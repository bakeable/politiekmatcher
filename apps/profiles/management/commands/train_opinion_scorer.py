import os
import json
import shutil
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import connections
from sklearn.model_selection import train_test_split
from torch import FloatTensor
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    Trainer,
    TrainingArguments,
)

from apps.content.models import (
    StatementPosition,
    ProgramFragment,
    ExampleOpinion,
    PoliticalDimensions,
)  # for field names

from datasets import Dataset

DIM_FIELDS = [
    "economic",
    "social",
    "environmental",
    "immigration",
    "europe",
    "authority",
    "institutionality",
]


class Command(BaseCommand):
    help = "Fine-tune a transformer to predict political dimensions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-creation of the model even if it already exists.",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Clean up training artifacts after saving the model.",
        )
        return super().add_arguments(parser)

    def handle(self, *args, **options):
        ##############################################################
        # 1. Pull & consolidate data
        ##############################################################
        objs = (
            list(StatementPosition.objects.filter(dimensions__isnull=False))
            + list(ProgramFragment.objects.filter(dimensions__isnull=False))
            + list(ExampleOpinion.objects.filter(dimensions__isnull=False))
        )

        records: List[Dict] = []
        for obj in objs:
            if isinstance(obj, StatementPosition):
                text = f"""
                Stelling: {obj.statement.text}
                Reactie: {obj.explanation}
                """
            elif isinstance(obj, ProgramFragment):
                text = f"""
                Text: {obj.content}
                """
            elif isinstance(obj, ExampleOpinion):
                statement = obj.statements.first()
                if statement:
                    text = f"""
                    Stelling: {statement.text}
                    Reactie: {obj.text}
                    """
                else:
                    # Fallback if no statement is linked
                    text = obj.text
            else:
                continue

            dims: PoliticalDimensions = obj.dimensions
            y = [getattr(dims, f) for f in DIM_FIELDS]
            # Drop items with missing values
            if None in y:
                continue
            records.append({"text": text, **dict(zip(DIM_FIELDS, y))})

        df = pd.DataFrame(records)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(df):,} labelled texts"))

        if len(df) < 300:  # empirical lower-bound for fine-tuning
            self.stdout.write(self.style.ERROR("Too few examples; aborting."))
            return

        ##############################################################
        # 2. Train/val/test split
        ##############################################################
        train_df, tmp = train_test_split(
            df, test_size=0.2, random_state=42, shuffle=True
        )
        val_df, test_df = train_test_split(tmp, test_size=0.5, random_state=42)

        ##############################################################
        # 3. Tokeniser & model
        ##############################################################
        model_name = "pdelobelle/robbert-v2-dutch-base"
        tok = AutoTokenizer.from_pretrained(model_name)

        def tokenize(batch):
            return tok(
                batch["text"],
                padding="max_length",
                truncation=True,
                max_length=256,
            )

        for dim in DIM_FIELDS:
            self.stdout.write(self.style.WARNING(f"\nTraining model for: {dim}"))

            # Prepare dataset with single-dimension labels
            def extract_label(example):
                example["label"] = float(example[dim])
                return example

            train_ds = (
                Dataset.from_pandas(train_df)
                .map(tokenize, batched=True)
                .map(extract_label)
            )
            val_ds = (
                Dataset.from_pandas(val_df)
                .map(tokenize, batched=True)
                .map(extract_label)
            )
            test_ds = (
                Dataset.from_pandas(test_df)
                .map(tokenize, batched=True)
                .map(extract_label)
            )

            model = AutoModelForSequenceClassification.from_pretrained(
                model_name,
                num_labels=1,
                problem_type="regression",
            )

            out_dir = Path("models") / f"political_dimensions_{dim}"
            args = TrainingArguments(
                output_dir=str(out_dir),
                per_device_train_batch_size=8,
                per_device_eval_batch_size=8,
                learning_rate=2e-5,
                num_train_epochs=20,
                weight_decay=0.01,
                evaluation_strategy="epoch",
                save_strategy="epoch",
                load_best_model_at_end=True,
                metric_for_best_model="eval_loss",
                fp16=False,
                report_to="none",
            )

            def compute_metrics(eval_pred):
                preds, labels = eval_pred
                mse = ((preds.flatten() - labels.flatten()) ** 2).mean()
                mae = np.abs(preds.flatten() - labels.flatten()).mean()
                return {
                    "mse": mse,
                    "mae": mae,
                }

            trainer = Trainer(
                model=model,
                args=args,
                train_dataset=train_ds,
                eval_dataset=val_ds,
                compute_metrics=compute_metrics,
            )

            trainer.train()
            self.stdout.write(self.style.SUCCESS(f"Training for '{dim}' complete."))

            metrics = trainer.evaluate(eval_dataset=test_ds)
            self.stdout.write(
                self.style.SUCCESS(f"{dim} metrics:\n{json.dumps(metrics, indent=2)}")
            )

            model.save_pretrained(out_dir)
            tok.save_pretrained(out_dir)
            self.stdout.write(
                self.style.SUCCESS(f"Saved model for '{dim}' to {out_dir}")
            )

            # Clean up checkpoint artifacts
            if options["cleanup"]:
                for sub in out_dir.glob("checkpoint-*"):
                    shutil.rmtree(sub)

                for extra in [
                    "trainer_state.json",
                    "training_args.bin",
                    "optimizer.pt",
                    "scheduler.pt",
                    "rng_state.pth",
                ]:
                    f = out_dir / extra
                    if f.exists():
                        f.unlink()
                self.stdout.write(
                    self.style.SUCCESS(f"Cleaned up training artifacts in {out_dir}")
                )
