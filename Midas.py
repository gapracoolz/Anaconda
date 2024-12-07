import usb.core
import usb.util
import usb.backend.libusb1
import subprocess
import ctypes
import winreg
import platform
import os
import json
import psutil

class CoinConfig:
    RANDOMX_COINS = {
        "MONERO": {
            "symbol": "XMR",
            "pools": [
                "xmr-asia1.nanopool.org:10300",
                "pool.supportxmr.com:3333",
                "xmr.2miners.com:2222"
            ]
        },
        "ARQMA": {
            "symbol": "ARQ",
            "pools": [
                "arqma.herominers.com:10641",
                "arq.pool-pay.com:4441"
            ]
        },
        "LOKI": {
            "symbol": "OXEN",
            "pools": [
                "loki.herominers.com:10111",
                "pool.loki.hashvault.pro:3333"
            ]
        }
    }

    CRYPTONIGHT_COINS = {
        "HAVEN": {
            "symbol": "XHV",
            "algorithm": "cn-heavy/xhv",
            "pools": [
                "haven.herominers.com:10451",
                "pool.haven.hashvault.pro:3333"
            ]
        },
        "CONCEAL": {
            "symbol": "CCX",
            "algorithm": "cn/ccx",
            "pools": [
                "conceal.herominers.com:10361",
                "pool.conceal.network:3333"
            ]
        }
    }

class MidasDongleDetector:
    def __init__(self):
        self.VENDOR_ID = 0x16C0
        self.PRODUCT_ID = 0x05DC
        self.device_info = None

    def list_usb_devices(self):
        try:
            devices = usb.core.find(find_all=True)
            found = False
            for device in devices:
                print(f"Device: VID={hex(device.idVendor)}, PID={hex(device.idProduct)}")
                if device.idVendor == self.VENDOR_ID and device.idProduct == self.PRODUCT_ID:
                    print("Midas Dongle Found")
                    found = True
            return found
        except Exception as e:
            print(f"Error listing USB devices: {e}")
            return False

    def verify_driver(self):
        try:
            path = f"SYSTEM\\CurrentControlSet\\Enum\\USB\\VID_{self.VENDOR_ID:04X}&PID_{self.PRODUCT_ID:04X}"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
            
            driver_key = winreg.OpenKey(key, "Device Parameters")
            driver_path = winreg.QueryValueEx(driver_key, "DriverPath")[0]
            
            if "winusb" in driver_path.lower():
                print("WinUSB driver properly installed")
                return True
            else:
                print("WinUSB driver not found. Please install using Zadig")
                return False
                
        except WindowsError:
            print("Could not verify driver. Please check device installation")
            return False

class XMRigManager:
    def __init__(self):
        self.xmrig_version = "6.19.2"
        self.base_url = f"https://github.com/xmrig/xmrig/releases/download/v{self.xmrig_version}/"
        self.xmrig_path = self._get_xmrig_path()

    def _get_xmrig_path(self):
        return "./xmrig.exe" if platform.system().lower() == "windows" else "./xmrig"

    def download_and_setup(self):
        if os.path.exists(self.xmrig_path):
            return True

        system = platform.system().lower()
        filename = f"xmrig-{self.xmrig_version}-msvc-win64.zip" if system == "windows" else f"xmrig-{self.xmrig_version}-linux-x64.tar.gz"

        try:
            print(f"Downloading XMRig {self.xmrig_version}...")
            import requests
            response = requests.get(self.base_url + filename, stream=True)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                if filename.endswith('.tar.gz'):
                    import tarfile
                    with tarfile.open(filename, 'r:gz') as tar:
                        tar.extractall()
                else:
                    import zipfile
                    with zipfile.ZipFile(filename, 'r') as zip_ref:
                        zip_ref.extractall()

                if system != "windows":
                    os.chmod(self.xmrig_path, 0o755)

                return True
            return False
        except Exception as e:
            print(f"Error downloading XMRig: {e}")
            return False

class MidasMiner:
    def __init__(self):
        self.detector = MidasDongleDetector()
        self.device = None
        self.backend = None
        self.xmrig = XMRigManager()
        self.init_status = self.initialize_device()

    def initialize_device(self):
        try:
            if not self.detector.list_usb_devices():
                raise ValueError("Midas dongle not found")

            if not self.detector.verify_driver():
                raise ValueError("WinUSB driver not properly installed")

            self.backend = usb.backend.libusb1.get_backend()
            if self.backend is None:
                raise ValueError("LibUSB backend not available")

            self.device = usb.core.find(
                idVendor=self.detector.VENDOR_ID,
                idProduct=self.detector.PRODUCT_ID,
                backend=self.backend
            )

            if self.device is None:
                raise ValueError("Could not initialize Midas device")

            self.device.set_configuration()
            
            print("Midas device successfully initialized")
            return True

        except Exception as e:
            print(f"Initialization error: {e}")
            return False

    def test_connection(self):
        if not self.init_status:
            return False

        try:
            self.device.ctrl_transfer(
                bmRequestType=0x80,
                bRequest=0x06,
                wValue=0x0100,
                wIndex=0x0000,
                data_or_wLength=18
            )
            print("USB connection test successful")
            return True
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    def generate_config(self, coin, wallet_address, pool_url):
        if coin in CoinConfig.RANDOMX_COINS:
            algo_config = {
                "randomx": {
                    "init": -1,
                    "mode": "auto",
                    "1gb-pages": False,
                    "rdmsr": True,
                    "wrmsr": True,
                    "numa": True
                }
            }
        elif coin in CoinConfig.CRYPTONIGHT_COINS:
            algo_config = {
                "algo": CoinConfig.CRYPTONIGHT_COINS[coin]["algorithm"],
                "cn": {
                    "enabled": True,
                    "priority": 1
                }
            }
        else:
            raise ValueError(f"Unsupported coin: {coin}")

        config = {
            "pools": [
                {
                    "url": pool_url,
                    "user": wallet_address,
                    "pass": "x",
                    "keepalive": True,
                    "tls": False
                }
            ],
            "cpu": True,
            "opencl": False,
            "cuda": False,
            **algo_config
        }

        return config

    def start_mining(self, coin, wallet_address, pool_url=None):
        if not self.xmrig.download_and_setup():
            raise RuntimeError("Failed to setup XMRig")

        if coin not in CoinConfig.RANDOMX_COINS and coin not in CoinConfig.CRYPTONIGHT_COINS:
            raise ValueError(f"Unsupported coin: {coin}")

        if pool_url is None:
            pool_url = (CoinConfig.RANDOMX_COINS.get(coin) or CoinConfig.CRYPTONIGHT_COINS.get(coin))["pools"][0]

        config = self.generate_config(coin, wallet_address, pool_url)
        
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)

        try:
            print(f"Starting {coin} mining on {pool_url}...")
            mining_process = subprocess.Popen(
                [self.xmrig.xmrig_path, '--config=config.json'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            while True:
                output = mining_process.stdout.readline()
                if output:
                    print(output.strip())
                if mining_process.poll() is not None:
                    break

        except KeyboardInterrupt:
            print("\nStopping miner...")
            mining_process.terminate()
        except Exception as e:
            print(f"Mining error: {e}")

def check_system_requirements():
    requirements = {
        "RAM": {
            "required": 4,
            "available": psutil.virtual_memory().total / (1024**3)
        },
        "CPU_Cores": {
            "required": 2,
            "available": psutil.cpu_count()
        },
        "Disk_Space": {
            "required": 2,
            "available": psutil.disk_usage('/').free / (1024**3)
        }
    }
    
    print("\nSystem Requirements Check:")
    all_passed = True
    for req, values in requirements.items():
        status = values["available"] >= values["required"]
        print(f"{req}: {'✓' if status else '✗'} "
              f"(Required: {values['required']}, "
              f"Available: {values['available']:.2f})")
        all_passed &= status
    
    return all_passed

def setup_mining_environment():
    directories = ['logs', 'config', 'data']
    for dir_name in directories:
        os.makedirs(dir_name, exist_ok=True)
    
    config_path = 'config/mining_config.json'
    default_config = {
        "auto_restart": True,
        "max_temp": 75,
        "power_limit": 80,
        "log_level": "INFO"
    }
    
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)

def main():
    try:
        print("Midas Mining System Initialization")
        print("---------------------------------")

        if not check_system_requirements():
            print("\nSystem requirements not met!")
            return

        setup_mining_environment()
        
        miner = MidasMiner()
        
        if not miner.init_status:
            print("\nDevice initialization failed. Troubleshooting steps:")
            print("1. Ensure device is properly connected")
            print("2. Check Windows Device Manager")
            print("3. Reinstall WinUSB driver using Zadig")
            print("4. Run program as Administrator")
            return

        if not miner.test_connection():
            print("\nUSB connection test failed")
            return

        print("\nDevice Information:")
        print(f"Vendor ID: 0x{miner.detector.VENDOR_ID:04X}")
        print(f"Product ID: 0x{miner.detector.PRODUCT_ID:04X}")

        print("\nAvailable coins:")
        all_coins = {**CoinConfig.RANDOMX_COINS, **CoinConfig.CRYPTONIGHT_COINS}
        for idx, (coin, data) in enumerate(all_coins.items(), 1):
            print(f"{idx}. {coin} ({data['symbol']})")
        
        while True:
            try:
                coin_choice = int(input("\nSelect coin number to mine: "))
                if 1 <= coin_choice <= len(all_coins):
                    break
                print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a number.")

        coin = list(all_coins.keys())[coin_choice-1]
        
        wallet = input("Enter your wallet address: ")
        if not wallet:
            print("Wallet address cannot be empty!")
            return

        miner.start_mining(coin, wallet)

    except KeyboardInterrupt:
        print("\nMining stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        print("\nPlease check all connections and try again")

if __name__ == "__main__":
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("Please run as Administrator!")
        input("Press Enter to exit...")
    else:
        main()
