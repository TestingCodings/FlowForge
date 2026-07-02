import sys
from pathlib import Path

# Allow `import main` and `import evaluator` from the rules-service root
sys.path.insert(0, str(Path(__file__).parent))
