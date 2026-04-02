import numpy as np
import os
import json
from pathlib import Path

class Output(dict):
    """
    Output is a subclass of dict used to store and process experiment results.
    It provides helper methods for formatting, extracting, saving, and loading data.
    """

    def __str__(self):
        """
        Returns:
          A string representation of the output data with each key-value pair on a new line.
        """
        lines = []
        for key, value in self.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _format(self, data):
        # 1) Structured arrays with a single field named 'value'
        if isinstance(data, np.ndarray) and data.dtype.fields is not None:
            if len(data.dtype) == 1:
                # unwrap the single field
                return data["value"]

        # 2) 0-dimensional arrays â†’ scalar
        if isinstance(data, np.ndarray) and data.ndim == 0:
            return data.item()

        # 3) 1-D single-element arrays â†’ scalar (optional)
        if isinstance(data, np.ndarray) and data.ndim == 1 and data.size == 1:
            return data[0]

        return data

    def extract(self, *keys, default=None):
        """
        Extracts and returns the values associated with the given keys.
        
        Inputs:
        *keys: a variable number of keys to extract.
        default: default value to return if key is not found.
        
        Returns:
        The formatted value if only one key is provided, 
        or a tuple of formatted values if multiple keys are given.
        """
        values = []
        for key in keys:
            if key not in self:
                if default is None:
                    raise KeyError(f"Key '{key}' not found in object.")
                value = default
            else:
                value = self[key]
            values.append(self._format(value))
        
        # If there's only one value, return it directly rather than in a tuple.
        if len(keys) == 1:
            return values[0]
        return tuple(values)
    
    def save(self, path):
        """
        Saves the output dictionary to a compressed .npz file.
        
        Inputs:
          path: the file path (including filename) where the data should be saved.
        """
        target = Path(path)
        from qubox.core.persistence import split_output_for_persistence
        arrays, meta, dropped = split_output_for_persistence(self)
        if dropped:
            meta["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }

        np.savez_compressed(target, **arrays)
        with open(target.with_suffix(".meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, default=str)

    def load(self, path):
        """
        Loads data from a .npz file into the dictionary.
        
        Inputs:
          path: the file path to the .npz file.
          
        Raises:
          FileNotFoundError if the file does not exist.
        """
        if os.path.exists(path):
            data = np.load(path, allow_pickle=True)
            self.clear()
            self.update({key: data[key] for key in data.files})
        else:
            raise FileNotFoundError(f"File {path} not found")
    
    @classmethod
    def from_file(cls, path: str) -> "Output":
        """
        Classâ€method constructor: load an .npz file into a new Output.

        Raises FileNotFoundError if the file does not exist.
        """
        inst = cls()
        inst.load(path)
        return inst

    @classmethod
    def merge(cls, outputs: list["Output"]) -> "Output":
        """
        Merges a list of Output instances into a single Output.

        For keys where all values are NumPy arrays, concatenates them.
        For other types, collects them in a list.

        Parameters:
            outputs (list[Output]): List of Output instances to merge.

        Returns:
            Output: A new Output instance with merged values.
        """
        if not outputs:
            return cls()

        keys = outputs[0].keys()
        merged = cls()

        for key in keys:
            values = [out[key] for out in outputs]
            if all(isinstance(v, np.ndarray) for v in values):
                merged[key] = np.concatenate(values)
            else:
                merged[key] = values  # or raise error if inconsistent
        return merged
    
    
class OutputArray(np.ndarray):
    """
    N-D array whose elements are Output instances.
    Adds an .extract(...) method that vectorizes Output.extract.
    """

    def __new__(cls, input_array):
        # Force object dtype, then view as OutputArray
        obj = np.asarray(input_array, dtype=object).view(cls)

        # Optional: sanity check â€“ all elements are Output
        for x in obj.ravel():
            if not isinstance(x, Output):
                raise TypeError("All elements of OutputArray must be Output instances.")
        return obj

    def extract(self, *keys, default=None):
        """
        Vectorized version of Output.extract over the array elements.

        Returns:
            If one key: ndarray with same shape as self.
            If multiple keys: tuple of ndarrays with same shape.
        """
        flat = self.ravel()

        def get(o, key):
            if key in o:
                return o._format(o[key])
            if default is not None:
                return default
            raise KeyError(f"Key '{key}' not found in one of the Output objects.")

        if len(keys) == 1:
            k = keys[0]
            vals = [get(o, k) for o in flat]
            return np.array(vals, dtype=object).reshape(self.shape)
        else:
            arrays = []
            for k in keys:
                vals = [get(o, k) for o in flat]
                arrays.append(np.array(vals, dtype=object).reshape(self.shape))
            return tuple(arrays)
