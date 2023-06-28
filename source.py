from typing import Any

import os
import json


class DataTypes:
    tickets = "tickets"
    settings = "settings"


class DataSource:
    def save(self, data_type: str, data: Any):
        """ Saves the data """
        pass

    def load(self, data_type: str) -> Any:
        """ Loads the data """
        pass


class JsonDataSource(DataSource):
    path: str

    def __init__(self, file_name: str):
        self.path = f"{os.getcwd()}/{file_name}"
        if not os.path.exists(self.path):
            open(self.path, "x").close()

    def load(self, data_type: str) -> Any:
        return self.load_all().get(data_type)

    def save(self, data_type: str, data: Any):
        with open(self.path, "w") as file:
            all_data = self.load_all()
            all_data[data_type] = data
            file.write(json.dumps(all_data))

    def load_all(self):
        with open(self.path, "r") as file:
            lines = file.readlines()
            dat = "".join(lines)
            if len(lines) == 0:
                return {}
            else:
                return json.loads(dat)
