#!/bin/bash
pip install -r requirements.txt
python -m flask db upgrade && your_actual_build_command