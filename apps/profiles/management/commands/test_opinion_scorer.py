from django.core.management.base import BaseCommand
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

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
    help = "Interactive prediction of political dimensions using per-dimension fine-tuned models."

    def handle(self, *args, **options):
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load tokenizers and models per dimension
        models = {}
        tokenizers = {}
        for dim in DIM_FIELDS:
            model_path = f"models/political_dimensions_{dim}"
            tokenizers[dim] = AutoTokenizer.from_pretrained(model_path)
            model = AutoModelForSequenceClassification.from_pretrained(model_path)
            model.eval().to(device)
            models[dim] = model

        while True:
            text = input("\nEnter text to classify (or 'exit' to quit): ").strip()
            if text.lower() == "exit":
                break
            if not text:
                continue

            results = {}
            for dim in DIM_FIELDS:
                tok = tokenizers[dim]
                model = models[dim]
                inputs = tok(
                    text,
                    return_tensors="pt",
                    truncation=True,
                    padding="longest",
                    max_length=256,
                ).to(device)

                with torch.no_grad():
                    output = model(**inputs)
                    score = output.logits[0][0].item()
                    score = max(-1.0, min(1.0, score))
                    results[dim] = score

            print("\nPredicted political dimensions:")
            for dim, val in results.items():
                print(f"  • {dim:14s}: {val:+0.3f}")
