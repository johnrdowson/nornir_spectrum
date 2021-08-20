# nornir_spectrum

[Spectrum](https://www.broadcom.com/info/aiops/dx-spectrum) inventory plugin for [Nornir](https://github.com/nornir-automation/nornir).

## Installation

Not available on PyPi (yet), but can be install directly from GitHub as follows: 

```
pip install git+https://github.com/johnrdowson/nornir_spectrum#egg=nornir_spectrum
```

## Example Usage

### Using the Nornir configuration file

```yaml
---
inventory:
  plugin: SpectrumInventory
  options:
    url: "https://oneclick.local"
    username: "spectrum_user"
    password: "spectrum_pass"
```

### Using the InitNornir function

```python
from nornir import InitNornir
from nornir_spectrum.plugins.inventory.spectrum import SpectrumInventory

nr = InitNornir(
    inventory={
        "plugin": "SpectrumInventory"
        "options": {
            "url": "https://oneclick.local",
            "username": "spectrum_user",
            "password": "spectrum_pass"
        }
    }

)
```

### Environment Variables

Rather than specifying the Spectrum URL, username and password in the script or configuration file, you can use the following environment variables:

- `SPECTRUM_URL`
- `SPECTRUM_USERNAME`
- `SPECTRUM_PASSWORD`

### SpectrumInventory Arguments

- `verify` - (True/False) - Turn SSL verification on or off
- `proxies` - (Dict) - Passed to `requests` object