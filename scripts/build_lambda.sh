#!/usr/bin/env bash
# Builds lambda.zip for AWS Lambda (Python 3.12 runtime).
set -euo pipefail
rm -rf build lambda.zip && mkdir build
pip install -r requirements.txt -t build --quiet
cp -r publisher lambda_function.py build/
(cd build && zip -r ../lambda.zip . -x "*.pyc" "*__pycache__*" > /dev/null)
echo "Built lambda.zip. Handler: lambda_function.handler"
