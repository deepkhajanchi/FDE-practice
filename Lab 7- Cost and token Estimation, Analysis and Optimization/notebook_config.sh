#!/bin/bash -e
echo "STARTUP-SCRIPT: START"
sudo -u jupyter gcloud storage cp gs://<YOUR_GCP_PROJECT_ID>-bucket/code_assistant_cost_optimization.ipynb /home/jupyter/
sudo -u jupyter gcloud storage cp --recursive gs://<YOUR_GCP_PROJECT_ID>-bucket/code_assistant /home/jupyter/
sudo -u jupyter gcloud storage cp --recursive gs://<YOUR_GCP_PROJECT_ID>-bucket/assets /home/jupyter/
echo "STARTUP-SCRIPT: END"
