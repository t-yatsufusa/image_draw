import pandas as pd

def read_config(config_path):
    df = pd.read_excel(
        config_path,
        sheet_name="config",
        header=None
    )
    return df.set_index(0)[1].to_dict()
