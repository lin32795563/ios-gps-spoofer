"""Find location simulation service on iOS 26."""
import sys
sys.path.insert(0, "backend/src")

from pymobiledevice3.tunneld.api import get_tunneld_devices

print("Connecting to tunneld...")
devices = get_tunneld_devices()
rsd = devices[0]
print(f"Device: {rsd.product_type} iOS {rsd.product_version}")

# List ALL services, search for location/simulate/dvt
services = rsd.peer_info.get("Services", {})
print(f"\nTotal services: {len(services)}")

keywords = ["simulat", "location", "dvt", "developer", "dt.", "instrument"]
print("\n--- Location/Developer related services ---")
for name in sorted(services.keys()):
    if any(kw in name.lower() for kw in keywords):
        print(f"  {name}: {services[name]}")

# Also try DVT approach
print("\n--- Trying DVT service ---")
try:
    from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
    dvt = DvtSecureSocketProxyService(rsd)
    dvt.__enter__()
    print(f"DVT connected! Available channels:")
    # List available instruments
    print(dir(dvt))
    dvt.__exit__(None, None, None)
except Exception as e:
    print(f"DVT failed: {e}")

# Try the CLI approach
print("\n--- Trying pymobiledevice3 developer simulate-location ---")
try:
    from pymobiledevice3.services.simulate_location import DtSimulateLocation
    # Check the service name
    print(f"DtSimulateLocation.SERVICE_NAME = {DtSimulateLocation.SERVICE_NAME}")
except Exception as e:
    print(f"Error: {e}")

# Try direct service access for all "dt" services
print("\n--- All 'dt' or 'dev' services ---")
for name in sorted(services.keys()):
    if "dt" in name.lower() or "dev" in name.lower():
        print(f"  {name}: {services[name]}")
