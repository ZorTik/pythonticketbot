def load_data_safe(data, is_arr=False):
    if data is None:
        if is_arr:
            return []
        else:
            return {}

    return data
