#!/bin/bash
# KARBOTU Validation Runner - Linux/Mac Script

echo "================================================================================
KARBOTU v1 VALIDATION RUNNER
================================================================================
"

# Quant_Engine dizinine git
cd "$(dirname "$0")/.."

# Python path'i ayarla
export PYTHONPATH="$PWD"

# Validation'ı çalıştır
python -m tests.karbotu_validation_runner

# Hata kontrolü
if [ $? -ne 0 ]; then
    echo "
================================================================================
ERROR: Validation failed
================================================================================
"
    exit 1
fi

echo "
================================================================================
Validation complete! Check tests/karbotu_validation_report.txt for details.
================================================================================
"






