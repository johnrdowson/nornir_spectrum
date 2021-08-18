# nornir_spectrum

## Installation

```
pip install git+https://github.com/johnrdowson/nornir_spectrum
```

## Usage

```
from nornir import InitNornir
from nornir_spectrum.plugins.inventory.spectrum import SpectrumInventory
nr = InitNornir(inventory={"plugin": "SpectrumInventory"})
```