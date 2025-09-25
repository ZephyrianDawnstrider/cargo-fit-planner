from celery import shared_task
from .utils import mixed_bin_packing
import pandas as pd
import os

@shared_task
def optimize_packages_task(cargo_df_json, available_containers, output_dir):
    cargo_df = pd.read_json(cargo_df_json)
    containers_used, model_images, remaining_data = mixed_bin_packing(cargo_df, available_containers, output_dir)
    # Return the results
    return {
        'containers_used': containers_used,
        'model_images': model_images,
        'remaining_data': remaining_data.to_dict('records') if not remaining_data.empty else []
    }
