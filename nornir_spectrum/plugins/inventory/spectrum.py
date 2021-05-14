import re
from nornir.core.inventory import (
    Inventory,
    Group,
    Groups,
    Host,
    Hosts,
    Defaults,
    ParentGroups,
)
from typing import Optional, Union, List, Tuple, Dict
from pyspectrum import SpectrumClient

SPECTRUM_PORT_MAP = {"32": 22, "7": 22, "3": 23}


NETMIKO_MODEL_TYPE_MAP = {
    "Rtr_Cisco": "cisco_ios",
    "SwCiscoIOS": "cisco_ios",
    "CiscoNXOS": "cisco_nxos",
    "SwCat45xx": "cisco_ios",
    "HubCat29xx": "cisco_ios",
    "CiscoASA": "cisco_asa",
}

NETMIKO_DEVICE_TYPE_MAP = {"CiscoRT": "cisco_ios", "JuniperRT": "junos"}


def platform_calc(model_type_name: str, device_type: str) -> str:
    platform = NETMIKO_MODEL_TYPE_MAP.get(
        model_type_name,
        NETMIKO_DEVICE_TYPE_MAP.get(device_type),
    )
    if not platform and device_type:
        if re.search("Cisco", device_type):
            platform = "cisco_ios"
        elif re.search("Juniper", device_type):
            platform = "junos"

    return platform


def _process_data(hosts_data: List[Dict[str, str]]) -> Tuple[Hosts, Groups]:
    """
    Converts the parsed data from Spectrum and returns the host and groups data.
    The groups
    """

    # Placeholders for the hosts and groups data which will be popuated
    hosts = Hosts()
    groups = Groups()

    # Main loop to interate over each device model
    for device in hosts_data:

        # Extract the unique Global Collections for which this host is a member
        # of
        gc_str = device.pop("collections_model_name_string")
        gc_list = list(set(gc_str.split(":"))) if gc_str else []

        # Add each Global Collection as a group if it doesn't already exist
        for gc in gc_list:
            groups.setdefault(gc, Group(gc))

        port = SPECTRUM_PORT_MAP.get(device.get("ncm_potential_comm_modes"))

        if port:
            platform = platform_calc(
                device.get("model_type_name"), device.get("device_type")
            )
        else:
            continue

        # Telnet only Cisco devices need specific platform for Netmiko to work
        if port == 23 and platform == "cisco_ios":
            platform = "cisco_ios_telnet"

        # NETCONF for all Juniper devices
        if platform == "junos":
            port = 830

        hostname = device.pop("model_name")

        hosts[hostname] = Host(
            name=hostname,
            hostname=device.pop("network_address"),
            port=port,
            platform=platform,
            groups=ParentGroups([groups[gc] for gc in gc_list]),
            data={**device},
        )

    return (hosts, groups)


class SpectrumInventory:
    def __init__(
        self,
        filter_expr: Optional[str] = None,
        extra_attrs: Optional[List[Union[int, str]]] = [],
    ) -> None:
        self.conn = SpectrumClient()
        self.filter_expr = filter_expr
        self.extra_attrs = extra_attrs

    def load(self) -> Inventory:
        """ Retrieves the inventory of devices from Spectrum """

        # Attributes to collect for each devices (refer to pyspectrum for)
        attrs = [
            "device_type",
            "network_address",
            "condition",
            "model_class",
            "collections_model_name_string",
            "topology_model_name_string",
            "ncm_potential_comm_modes",
        ] + self.extra_attrs

        # When a filter expression is supplied, the 'fetch_models' method must
        # be used in order to specify this in the POST request.
        if self.filter_expr:
            data = self.conn.fetch_models(
                devices_only=True, filters=self.filter_expr, attrs=attrs
            ).result
        else:
            data = self.conn.fetch_all_devices(attrs=attrs).result

        hosts, groups = _process_data(data)

        return Inventory(hosts=hosts, groups=groups, defaults=Defaults())