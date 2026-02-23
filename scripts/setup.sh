#!/bin/bash
# Setup script for Fagan Inspection Tool

echo "=========================================="
echo "Fagan Inspection Tool - Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $python_version"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "ERROR: Python 3.11+ required"
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Install in development mode
echo ""
echo "Installing fagan-tool in development mode..."
pip install -e .

# Run tests
echo ""
echo "Running tests..."
pytest tests/ -v

# Check for API keys
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Set your API key:"
echo "   export ANTHROPIC_API_KEY='your-key-here'"
echo "   # or"
echo "   export OPENAI_API_KEY='your-key-here'"
echo ""
echo "3. Test the installation:"
echo "   fagan dry-run"
echo ""
echo "4. Place your artifacts in artifacts/input/"
echo ""
echo "5. Run an inspection:"
echo "   fagan run --config configs/examples/c1_ubr.yaml"
echo ""
echo "For more information, see README.md and USAGE_EXAMPLES.md"
echo ""
