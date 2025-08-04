"""
Django management command to download and setup a local LLM for fragment generation
"""

import os
import torch
from pathlib import Path
import psutil

from django.core.management.base import BaseCommand
from django.conf import settings

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    pipeline,
)
from huggingface_hub import snapshot_download, login


class LocalLLMManager:
    """Manages local LLM download, setup and configuration"""

    def __init__(self):
        self.models_dir = Path(settings.BASE_DIR) / "models"
        self.models_dir.mkdir(exist_ok=True)

        # Model configurations - ordered by preference
        self.available_models = {
            "llama-3.1-8b-instruct": {
                "model_id": "meta-llama/Meta-Llama-3.1-8B-Instruct",
                "size_gb": 16,
                "requires_auth": True,
                "description": "Meta's Llama 3.1 8B - Best quality, requires HF auth",
                "context_length": 128000,
            },
            "mixtral-8x7b-instruct": {
                "model_id": "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "size_gb": 45,
                "requires_auth": False,
                "description": "Mixtral 8x7B - Excellent quality, very large",
                "context_length": 32768,
            },
            "llama-3-8b-instruct": {
                "model_id": "meta-llama/Meta-Llama-3-8B-Instruct",
                "size_gb": 16,
                "requires_auth": True,
                "description": "Meta's Llama 3 8B - High quality, requires HF auth",
                "context_length": 8192,
            },
            "mistral-7b-instruct": {
                "model_id": "mistralai/Mistral-7B-Instruct-v0.3",
                "size_gb": 14,
                "requires_auth": False,
                "description": "Mistral 7B v0.3 - Good quality, no auth required",
                "context_length": 32768,
            },
            "zephyr-7b-beta": {
                "model_id": "HuggingFaceH4/zephyr-7b-beta",
                "size_gb": 14,
                "requires_auth": False,
                "description": "Zephyr 7B - Good instruction following, no auth",
                "context_length": 32768,
            },
            "openchat-3.5": {
                "model_id": "openchat/openchat-3.5-0106",
                "size_gb": 14,
                "requires_auth": False,
                "description": "OpenChat 3.5 - Fast and capable, no auth required",
                "context_length": 8192,
            },
            # Nederlandse modellen voor betere Nederlandse tekst
            "gpt2-small-dutch": {
                "model_id": "GroNLP/gpt2-small-dutch",
                "size_gb": 0.5,
                "requires_auth": False,
                "description": "GPT2 Small Nederlands - Compacte Nederlandse taalmodel, ideaal voor fragmentatie",
                "context_length": 1024,
            },
            "gpt-neo-1.3b-dutch": {
                "model_id": "yhavinga/gpt-neo-1.3B-dutch",
                "size_gb": 2.6,
                "requires_auth": False,
                "description": "GPT-Neo 1.3B Nederlands - Krachtig Nederlands model met goede tekstkwaliteit",
                "context_length": 2048,
            },
            "bert-base-dutch": {
                "model_id": "GroNLP/bert-base-dutch-cased",
                "size_gb": 0.4,
                "requires_auth": False,
                "description": "BERT Base Nederlands - Alleen voor begrip, niet voor tekstgeneratie",
                "context_length": 512,
            },
        }

    def check_system_requirements(self):
        """Check if system can handle LLM inference"""
        # Check available RAM
        ram_gb = psutil.virtual_memory().total / (1024**3)

        # Check if CUDA is available
        has_cuda = torch.cuda.is_available()
        if has_cuda:
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        else:
            gpu_memory = 0

        # Check available disk space
        disk_free = psutil.disk_usage(str(self.models_dir)).free / (1024**3)

        return {
            "ram_gb": ram_gb,
            "has_cuda": has_cuda,
            "gpu_memory_gb": gpu_memory,
            "disk_free_gb": disk_free,
        }

    def recommend_model(self, system_info, prefer_dutch=True):
        """Recommend best model based on system capabilities and language preference"""

        # Voor Nederlandse politieke content, prefereer Nederlandse modellen
        if prefer_dutch:
            # Kies op basis van beschikbare resources
            if system_info["disk_free_gb"] >= 3 and system_info["ram_gb"] >= 8:
                # GPT-Neo 1.3B heeft goede kwaliteit
                return "gpt-neo-1.3b-dutch"
            elif system_info["disk_free_gb"] >= 1:
                # GPT2 Small is het meest betrouwbare
                return "gpt2-small-dutch"

        # Fallback naar internationale modellen
        if system_info["has_cuda"] and system_info["gpu_memory_gb"] >= 24:
            # High-end GPU - can run large models
            if system_info["disk_free_gb"] >= 50:
                return "mixtral-8x7b-instruct"
            else:
                return "llama-3.1-8b-instruct"

        elif system_info["has_cuda"] and system_info["gpu_memory_gb"] >= 16:
            # Mid-range GPU - can run 8B models
            return "llama-3.1-8b-instruct"

        elif system_info["has_cuda"] and system_info["gpu_memory_gb"] >= 10:
            # Entry-level GPU - 7B models with quantization
            return "mistral-7b-instruct"

        elif system_info["ram_gb"] >= 32:
            # CPU-only but plenty of RAM
            return "zephyr-7b-beta"

        elif system_info["ram_gb"] >= 16:
            # Limited RAM - smallest capable model
            return "openchat-3.5"

        else:
            return None  # System not capable

    def download_model(self, model_key: str, force_download: bool = False):
        """Download and cache the specified model"""
        if model_key not in self.available_models:
            raise ValueError(f"Unknown model: {model_key}")

        model_config = self.available_models[model_key]
        model_id = model_config["model_id"]

        # Check if model already exists
        model_cache_dir = self.models_dir / model_key
        if model_cache_dir.exists() and not force_download:
            print(f"✅ Model {model_key} already downloaded at {model_cache_dir}")
            return str(model_cache_dir)

        print(f"📥 Downloading {model_key} ({model_config['size_gb']}GB)...")
        print(f"   Model ID: {model_id}")
        print(f"   Description: {model_config['description']}")

        # Handle authentication if required
        if model_config["requires_auth"]:
            print("🔐 This model requires Hugging Face authentication.")
            print("   Please make sure you have:")
            print("   1. A Hugging Face account")
            print("   2. Accepted the model license agreement")
            print(
                "   3. Set HF_TOKEN environment variable or run `huggingface-cli login`"
            )

            # Try to login if HF_TOKEN is available
            hf_token = os.getenv("HF_TOKEN")
            if hf_token:
                print("   Using HF_TOKEN environment variable...")
                login(token=hf_token, add_to_git_credential=False)
            else:
                print(
                    "   ⚠️  No HF_TOKEN found. You may need to run: huggingface-cli login"
                )

        try:
            # Download the model to our models directory
            snapshot_download(
                repo_id=model_id,
                local_dir=str(model_cache_dir),
                local_dir_use_symlinks=False,
                resume_download=True,
            )

            print(f"✅ Successfully downloaded {model_key}")
            return str(model_cache_dir)

        except Exception as e:
            print(f"❌ Failed to download {model_key}: {e}")
            if model_config["requires_auth"]:
                print("   💡 If this is an authentication error:")
                print("      1. Visit https://huggingface.co/settings/tokens")
                print("      2. Create a token with read permissions")
                print("      3. Run: export HF_TOKEN=your_token_here")
                print("      4. Or run: huggingface-cli login")
            raise

    def test_model_loading(self, model_path: str):
        """Test if model can be loaded and generate text"""
        print(f"🧪 Testing model loading from {model_path}...")

        try:
            # Determine quantization based on available GPU memory
            system_info = self.check_system_requirements()

            if system_info["has_cuda"] and system_info["gpu_memory_gb"] >= 16:
                # Load in full precision if we have enough GPU memory
                quantization_config = None
                device_map = "auto"
                torch_dtype = torch.float16
            elif system_info["has_cuda"]:
                # Use 4-bit quantization for smaller GPUs
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
                device_map = "auto"
                torch_dtype = None
            else:
                # CPU-only loading
                quantization_config = None
                device_map = None
                torch_dtype = torch.float32

            # Load tokenizer
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # Load model
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=quantization_config,
                device_map=device_map,
                torch_dtype=torch_dtype,
                trust_remote_code=True,
            )

            # Create pipeline
            generator = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_length=512,
                do_sample=True,
                temperature=0.1,
                pad_token_id=tokenizer.eos_token_id,
            )

            # Test generation - aangepast voor Nederlandse modellen
            if any(
                dutch_model in model_path for dutch_model in ["dutch", "nederlands"]
            ):
                test_prompt = "Klimaatbeleid in Nederland:"
                max_new_tokens = 50  # Nederlandse modellen zijn kleiner
            else:
                test_prompt = "Schrijf een korte samenvatting van het klimaatbeleid:"
                max_new_tokens = 100

            result = generator(
                test_prompt, max_new_tokens=max_new_tokens, num_return_sequences=1
            )

            print("✅ Model loaded successfully!")
            print(f"📝 Test generation:")
            print(f"   Input: {test_prompt}")
            print(
                f"   Output: {result[0]['generated_text'][len(test_prompt):].strip()}"
            )

            return True

        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            return False

    def create_llm_config(self, model_key: str, model_path: str):
        """Create configuration file for the LLM"""
        config = {
            "model_key": model_key,
            "model_path": model_path,
            "model_config": self.available_models[model_key],
            "system_info": self.check_system_requirements(),
        }

        config_file = self.models_dir / "llm_config.json"

        import json

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        print(f"⚙️  Created LLM configuration at {config_file}")
        return config_file


class Command(BaseCommand):
    help = "Download and setup a local LLM for political content fragmentation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            type=str,
            help='Specific model to download (e.g., "mistral-7b-instruct")',
        )
        parser.add_argument(
            "--prefer-dutch",
            action="store_true",
            default=True,
            help="Prefer Dutch language models for political content (default: True)",
        )
        parser.add_argument(
            "--international",
            action="store_true",
            help="Use international models instead of Dutch models",
        )
        parser.add_argument(
            "--list-models",
            action="store_true",
            help="List available models and exit",
        )
        parser.add_argument(
            "--force-download",
            action="store_true",
            help="Force re-download even if model exists",
        )
        parser.add_argument(
            "--test-only",
            action="store_true",
            help="Only test existing model, do not download",
        )
        parser.add_argument(
            "--check-system",
            action="store_true",
            help="Check system requirements and recommendations",
        )

    def handle(self, *args, **options):
        manager = LocalLLMManager()

        # Check system requirements first
        system_info = manager.check_system_requirements()

        self.stdout.write("🖥️  System Information:")
        self.stdout.write(f"   RAM: {system_info['ram_gb']:.1f} GB")
        self.stdout.write(f"   CUDA: {'Yes' if system_info['has_cuda'] else 'No'}")
        if system_info["has_cuda"]:
            self.stdout.write(f"   GPU Memory: {system_info['gpu_memory_gb']:.1f} GB")
        self.stdout.write(f"   Free Disk Space: {system_info['disk_free_gb']:.1f} GB")

        if options["check_system"]:
            prefer_dutch = options["prefer_dutch"] and not options["international"]
            recommended = manager.recommend_model(
                system_info, prefer_dutch=prefer_dutch
            )
            if recommended:
                self.stdout.write(f"\n🎯 Recommended model: {recommended}")
                model_config = manager.available_models[recommended]
                self.stdout.write(f"   Description: {model_config['description']}")
                self.stdout.write(f"   Size: {model_config['size_gb']} GB")
                self.stdout.write(
                    f"   Context length: {model_config['context_length']:,} tokens"
                )

                # Toon waarom dit model wordt aanbevolen
                if "dutch" in recommended or "nederlands" in recommended:
                    self.stdout.write(
                        "   🇳🇱 Nederlandse taalmodel - optimaal voor politieke content"
                    )
                else:
                    self.stdout.write(
                        "   🌍 Internationaal model - goede algemene prestaties"
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        "\n❌ Your system may not be suitable for running LLMs"
                    )
                )
                self.stdout.write(
                    "   Minimum requirements: 16GB RAM or CUDA GPU with 8GB+ VRAM"
                )
            return

        if options["list_models"]:
            self.stdout.write("\n📋 Available Models:")

            # Groepeer Nederlandse en internationale modellen
            dutch_models = {}
            international_models = {}

            for key, config in manager.available_models.items():
                if "dutch" in key or "nederlands" in key:
                    dutch_models[key] = config
                else:
                    international_models[key] = config

            # Toon Nederlandse modellen eerst
            if dutch_models:
                self.stdout.write(
                    "\n🇳🇱 Nederlandse Modellen (aanbevolen voor politieke content):"
                )
                for key, config in dutch_models.items():
                    auth_mark = "🔐" if config["requires_auth"] else "🌐"
                    self.stdout.write(f"\n{auth_mark} {key}")
                    self.stdout.write(f"   Model: {config['model_id']}")
                    self.stdout.write(f"   Size: {config['size_gb']} GB")
                    self.stdout.write(
                        f"   Context: {config['context_length']:,} tokens"
                    )
                    self.stdout.write(f"   Description: {config['description']}")

            # Toon internationale modellen
            if international_models:
                self.stdout.write("\n🌍 Internationale Modellen:")
                for key, config in international_models.items():
                    auth_mark = "🔐" if config["requires_auth"] else "🌐"
                    self.stdout.write(f"\n{auth_mark} {key}")
                    self.stdout.write(f"   Model: {config['model_id']}")
                    self.stdout.write(f"   Size: {config['size_gb']} GB")
                    self.stdout.write(
                        f"   Context: {config['context_length']:,} tokens"
                    )
                    self.stdout.write(f"   Description: {config['description']}")
            return

        # Determine which model to use
        if options["model"]:
            model_key = options["model"]
            if model_key not in manager.available_models:
                self.stdout.write(self.style.ERROR(f"❌ Unknown model: {model_key}"))
                self.stdout.write("Available models:")
                for key in manager.available_models.keys():
                    dutch_mark = "🇳🇱" if "dutch" in key or "nederlands" in key else "🌍"
                    self.stdout.write(f"   {dutch_mark} {key}")
                return
        else:
            # Auto-select based on system and language preference
            prefer_dutch = options["prefer_dutch"] and not options["international"]
            model_key = manager.recommend_model(system_info, prefer_dutch=prefer_dutch)
            if not model_key:
                self.stdout.write(
                    self.style.ERROR("❌ Cannot recommend a model for your system")
                )
                self.stdout.write(
                    "Please check system requirements with --check-system"
                )
                return

            language_type = (
                "Nederlands"
                if "dutch" in model_key or "nederlands" in model_key
                else "Internationaal"
            )
            self.stdout.write(
                f"\n🎯 Auto-selected model: {model_key} ({language_type})"
            )

        model_config = manager.available_models[model_key]
        self.stdout.write(f"📦 Target model: {model_config['description']}")

        # Check if we have enough disk space
        required_space = model_config["size_gb"] * 1.2  # 20% buffer
        if system_info["disk_free_gb"] < required_space:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Insufficient disk space. Need {required_space:.1f}GB, "
                    f"have {system_info['disk_free_gb']:.1f}GB"
                )
            )
            return

        try:
            # Test existing model if requested
            if options["test_only"]:
                model_path = manager.models_dir / model_key
                if not model_path.exists():
                    self.stdout.write(
                        self.style.ERROR(
                            f"❌ Model {model_key} not found at {model_path}"
                        )
                    )
                    return

                success = manager.test_model_loading(str(model_path))
                if success:
                    self.stdout.write(self.style.SUCCESS("✅ Model test successful!"))
                else:
                    self.stdout.write(self.style.ERROR("❌ Model test failed"))
                return

            # Download the model
            self.stdout.write(f"\n🚀 Starting download of {model_key}...")
            model_path = manager.download_model(
                model_key, force_download=options["force_download"]
            )

            # Test the downloaded model
            self.stdout.write(f"\n🧪 Testing model...")
            success = manager.test_model_loading(model_path)

            if success:
                # Create configuration
                config_file = manager.create_llm_config(model_key, model_path)

                self.stdout.write(
                    self.style.SUCCESS(f"\n🎉 Successfully set up local LLM!")
                )
                self.stdout.write(f"📁 Model location: {model_path}")
                self.stdout.write(f"⚙️  Config file: {config_file}")

                # Extra info voor Nederlandse modellen
                if "dutch" in model_key or "nederlands" in model_key:
                    self.stdout.write(
                        f"\n🇳🇱 Je hebt een Nederlands taalmodel geïnstalleerd!"
                    )
                    self.stdout.write(
                        f"   Dit model is geoptimaliseerd voor Nederlandse politieke teksten."
                    )
                    self.stdout.write(
                        f"   Verwacht betere resultaten bij fragmentatie van verkiezingsprogramma's."
                    )

                self.stdout.write(
                    f"\n💡 You can now use the fragment generation command:"
                )
                self.stdout.write(f"   python manage.py fragment_with_llm")
            else:
                self.stdout.write(
                    self.style.ERROR(
                        "❌ Model downloaded but failed to load. Please check the logs."
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Setup failed: {e}"))
            self.stdout.write("\n💡 Troubleshooting tips:")
            self.stdout.write("   1. Check your internet connection")
            self.stdout.write("   2. Ensure you have enough disk space")
            self.stdout.write(
                "   3. For auth-required models, set up HuggingFace token"
            )
            self.stdout.write(
                "   4. Try a smaller model if you have hardware limitations"
            )
