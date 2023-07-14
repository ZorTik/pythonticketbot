from typing import Any

import os
import json


def user_type_func(gid: int, uid: int):
    return f"user:{gid}:{uid}"


class DataTypes:
    tickets = "tickets"
    settings = "settings"
    user = user_type_func


class DataSource:
    def save(self, data_type: str, data: Any):
        """ Saves the data """
        pass

    def load(self, data_type: str) -> Any:
        """ Loads the data """
        pass


class JsonDataSource(DataSource):
    path: str
    data: Any

    def __init__(self, file_name: str):
        self.path = f"{os.getcwd()}/{file_name}"
        if not os.path.exists(self.path):
            print("data.json does not exist, creating...")
            self.recreate_file()
        self.data = self.load_all()

    def load(self, data_type: str) -> Any:
        return self.data.get(data_type)

    def save(self, data_type: str, data: Any):
        with open(self.path, "w") as file:
            all_data = self.data
            all_data[data_type] = data
            self.data = all_data
            file.write(json.dumps(all_data))

    def load_all(self, retries=1):
        dat: str
        with open(self.path, "r+") as file:
            dat = "".join(file.readlines())
        if len(dat) == 0:
            if retries > 3:
                print(f"Recreating data.json...")
                self.recreate_file()
                return self.load_all()
            else:
                retries += 1
                print(f"data.json is empty, retrying load... ({retries}nd try)")
                return self.load_all(retries)
        else:
            return json.loads(dat)

    def recreate_file(self):
        with open(self.path, "w+") as file:
            file.write("{}")
