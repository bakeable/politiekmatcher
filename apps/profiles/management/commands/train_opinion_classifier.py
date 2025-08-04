import os
import json

import torch

from sklearn.metrics import classification_report, confusion_matrix
from apps.utils.classifier import classify_opinion
import numpy as np
from django.core.management.base import BaseCommand, CommandError
from sklearn.model_selection import train_test_split
from transformers import (
    DistilBertTokenizerFast,
    DistilBertForSequenceClassification,
    Trainer,
    TrainingArguments,
)
from datasets import Dataset


def compute_metrics(p):
    preds = np.argmax(p.predictions, axis=1)
    labels = p.label_ids
    accuracy = (preds == labels).astype(np.float32).mean().item()
    return {"accuracy": accuracy}


class WeightedTrainer(Trainer):
    def __init__(self, *args, label_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_weights = label_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        # Extract labels and create a copy of inputs without labels
        inputs_copy = inputs.copy()
        labels = inputs_copy.pop("labels")
        # Forward pass
        outputs = model(**inputs_copy)
        logits = outputs.logits
        # Compute weighted loss
        loss_fct = torch.nn.CrossEntropyLoss(
            weight=self.label_weights.to(logits.device)
        )
        loss = loss_fct(logits.view(-1, model.config.num_labels), labels.view(-1))
        return (loss, outputs) if return_outputs else loss


class Command(BaseCommand):
    help = (
        "Fine-tune a pretrained Transformer to classify user reactions "
        "(agree, neutral, disagree) from example_opinions.jsonl."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model_name",
            type=str,
            default="distilbert-base-uncased",
            help="Hugging Face model identifier to fine-tune from",
        )
        parser.add_argument(
            "--data_file",
            type=str,
            default="data/example_opinions.jsonl",
            help="Path to JSONL with fields: text, label, statement",
        )
        parser.add_argument(
            "--output_dir",
            type=str,
            default="models/opinion_classifier",
            help="Directory to save the fine-tuned model",
        )
        parser.add_argument(
            "--epochs", type=int, default=100, help="Number of training epochs"
        )
        parser.add_argument(
            "--batch-size", type=int, default=16, help="Per-device batch size"
        )
        parser.add_argument(
            "--confusion_matrix",
            action="store_true",
            help="Whether to display the confusion matrix",
        )
        parser.add_argument(
            "--labels",
            nargs="+",
            default=["disagree", "neutral", "agree"],
            help="Labels for classification (default: disagree neutral agree)",
        )

    def confusion_matrix(self, options):
        data_file = options["data_file"]
        labels = options["labels"]

        if not os.path.exists(data_file):
            raise CommandError(f"Data file not found: {data_file}")

        y_true = []
        y_pred = []

        # Load test records
        with open(data_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                true_label = rec.get("label", "").lower()
                stmt = rec.get("statement", "").strip()
                reaction = rec.get("text", "").strip()

                if true_label not in labels or not stmt or not reaction:
                    continue

                pred, _ = classify_opinion(stmt, reaction)
                y_true.append(true_label)
                y_pred.append(pred)

        if not y_true:
            raise CommandError("No valid test records found.")

        # Compute confusion matrix
        cm = confusion_matrix(y_true, y_pred, labels=labels)
        self.stdout.write("\nConfusion Matrix (rows=true, cols=predicted):")

        # Format matrix
        header = "      " + "  ".join(f"{l:^7}" for l in labels)
        self.stdout.write(header)
        for i, row in enumerate(cm):
            row_str = "  ".join(f"{val:^7}" for val in row)
            self.stdout.write(f"{labels[i]:<9}{row_str}")

        # Classification report
        report = classification_report(y_true, y_pred, labels=labels, zero_division=0)
        self.stdout.write("\nClassification Report:")
        self.stdout.write(report)

    def handle(self, *args, **options):
        model_name = options["model_name"]
        data_file = options["data_file"]
        output_dir = options["output_dir"]
        epochs = options["epochs"]
        batch_size = options["batch_size"]

        if not os.path.exists(data_file):
            raise CommandError(f"Data file not found: {data_file}")

        if options["confusion_matrix"]:
            self.confusion_matrix(options)
            return

        texts, labels = [], []
        label2id = {"disagree": 0, "neutral": 1, "agree": 2}

        # Load data from JSONL
        with open(data_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    stmt = rec.get("statement", "").strip()
                    user_txt = rec.get("text", "").strip()
                    label = rec.get("label", "").lower()
                except json.JSONDecodeError:
                    continue
                if not stmt or not user_txt or label not in label2id:
                    continue
                texts.append(f"Stelling: {stmt}\nReactie: {user_txt}")
                labels.append(label2id[label])

        if not texts:
            raise CommandError("No valid records loaded from data file.")

        # Train/validation split
        X_train, X_val, y_train, y_val = train_test_split(
            texts,
            labels,
            test_size=0.2,
            stratify=labels,
            random_state=42,
        )

        # Compute class weights to address imbalance
        counts = np.bincount(y_train)
        total_samples = len(y_train)
        class_weights = [
            total_samples / (len(counts) * c) if c > 0 else 0.0 for c in counts
        ]
        class_weights = torch.tensor(class_weights, dtype=torch.float)

        # Load tokenizer and model
        tokenizer = DistilBertTokenizerFast.from_pretrained(model_name)
        model = DistilBertForSequenceClassification.from_pretrained(
            model_name, num_labels=3
        )

        # Prepare Hugging Face datasets
        def tokenize_fn(batch):
            return tokenizer(batch["text"], padding="max_length", truncation=True)

        train_ds = Dataset.from_dict({"text": X_train, "label": y_train})
        val_ds = Dataset.from_dict({"text": X_val, "label": y_val})
        train_ds = train_ds.map(tokenize_fn, batched=True)
        val_ds = val_ds.map(tokenize_fn, batched=True)
        train_ds.set_format(
            type="torch", columns=["input_ids", "attention_mask", "label"]
        )
        val_ds.set_format(
            type="torch", columns=["input_ids", "attention_mask", "label"]
        )

        # Training arguments
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            logging_steps=50,
            load_best_model_at_end=True,
            metric_for_best_model="accuracy",
            greater_is_better=True,
        )

        trainer = WeightedTrainer(
            model=model,
            args=training_args,
            train_dataset=train_ds,
            eval_dataset=val_ds,
            compute_metrics=compute_metrics,
            label_weights=class_weights,
        )

        self.stdout.write("Starting fine-tuning...")
        trainer.train()
        self.stdout.write("Fine-tuning complete. Saving model and tokenizer...")

        os.makedirs(output_dir, exist_ok=True)
        trainer.save_model(output_dir)
        tokenizer.save_pretrained(output_dir)

        self.stdout.write(
            self.style.SUCCESS(f"Model and tokenizer saved to {output_dir}")
        )

        # Clean up checkpoints and training files
        import shutil

        for file in os.listdir(output_dir):
            path = os.path.join(output_dir, file)
            if file.startswith("checkpoint-") and os.path.isdir(path):
                shutil.rmtree(path)

        self.stdout.write(
            self.style.SUCCESS("Cleaned up checkpoint files in output directory.")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Fine-tuned model ready at {output_dir}. You can now use it for predictions."
            )
        )

        self.confusion_matrix(options)
