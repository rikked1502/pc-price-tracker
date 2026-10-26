"""python -m unittest test_specs"""
import unittest

from specs import SLOTS, extract


def want(**kw):
    return {s: None for s in SLOTS} | {"peripherals": [], "check": [], "unknown": []} | kw


class Extract(unittest.TestCase):
    def check(self, text, **kw):
        self.assertEqual(extract(text), want(**kw))

    def test_apu_build_no_gpu(self):
        self.check("""FOR SALE GAMING PC 🔥
🔹CPU: Ryzen 5 5600G
🔹Mobo: Asrock B450M Steel Legend
🔹Ram 16gb (8x2) 3200mhz
🔹500gb nvme
🔹PSU 650w bronze
🔹Case: Tecware Forge M
Stock cooler lang
No GPU (APU build) pero kaya valorant
pm for price""",
                   cpu="Ryzen 5600G", ram="16GB DDR4", ssd="SSD 500GB", board="B450 Motherboard", psu="PSU 650W",
                   cooler="stock", case="Tecware Forge M")

    def test_intel_gen_rtx3060_no_vram(self):
        self.check("""RUSH!! i5 12th gen + RTX 3060
Ram 16gb
SSD 512gb
Negotiable, meet up Cubao""",
                   cpu="i5 12th Gen", gpu="RTX 3060", ram="16GB DDR4", ssd="SSD 512GB",
                   check=["gpu size unknown: RTX 3060 (8/12GB)", "ram DDR guessed", "cpu generation only"])

    def test_complete_set_with_monitor(self):
        self.check("""COMPLETE SET GAMING PC
• Ryzen 5 3600
• RX 580 8gb
• 16gb ddr4 3200mhz
• 256gb ssd
• Monitor 24" 165hz
• free keyboard & mouse + mousepad
With box pa yung gpu""",
                   cpu="Ryzen 3600", gpu="RX 580 8GB", ram="16GB DDR4", ssd="SSD 256GB", monitor="Monitor 24in 165Hz",
                   peripherals=["keyboard", "mouse", "mousepad"])

    def test_complete_set_monitor_not_itemized(self):
        self.check("Complete set na po! i3 10100f, gtx 1650, 8gb ddr4, 240gb ssd, may monitor keyboard mouse at avr",
                   cpu="i3-10100F", gpu="GTX 1650", ram="8GB DDR4", ssd="SSD 240GB", peripherals=["avr", "keyboard", "mouse"],
                   check=["set: monitor not itemized"])

    def test_unit_only_no_monitor(self):
        self.check("""SYSTEM UNIT ONLY
- Intel Core i5-10400F
- GTX 1660 Super 6gb
- 8gb ddr4
- 1TB HDD
No monitor, no keyboard. Swap sa laptop pwede""",
                   cpu="i5-10400F", gpu="GTX 1660 Super", ram="8GB DDR4")

    def test_ddr5_am5_ram_gen_guessed(self):
        self.check("""AM5 BUILD
CPU - Ryzen 5 7600
Mobo - Gigabyte B650M DS3H
RAM - 32gb (16x2) 6000
GPU - RX 7600 8gb
1TB NVMe Gen4
PSU 650w 80+ bronze
Cooler - Deepcool AK400""",
                   cpu="Ryzen 7600", gpu="RX 7600", ram="32GB DDR5", ssd="SSD 1TB", board="B650 Motherboard",
                   psu="PSU 650W", cooler="air", check=["ram DDR guessed"])

    def test_core_ultra_guesses_ddr5(self):
        self.check("Core Ultra 7 265K | RTX 5070 | 32gb ram | 2tb nvme | 360mm aio | 850w gold psu",
                   cpu="Ultra 265K", gpu="RTX 5070", ram="32GB DDR5", ssd="SSD 2TB", psu="PSU 850W", cooler="aio",
                   check=["ram DDR guessed"])

    def test_ram_gen_stated_on_another_line(self):
        self.check("Ryzen 5 5600\nB550M DDR4 mobo\nMemory: 16GB\nRTX 3060 12gb",
                   cpu="Ryzen 5600", gpu="RTX 3060 12GB", ram="16GB DDR4", board="B550 Motherboard")

    def test_negations(self):
        self.check("""Selling my pc, no ssd (transfer ko sa bago), walang gpu
Ryzen 7 5700X
32gb ddr4 3600mhz
Walang monitor""",
                   cpu="Ryzen 5700X", ram="32GB DDR4")

    def test_messy_one_line_plus(self):
        self.check("r5 5600x+rtx 3070 ti+16gb ddr4+1tb nvme+1tb hdd+b550m+650w psu+ tecware case rush 35k",
                   cpu="Ryzen 5600X", gpu="RTX 3070 Ti", ram="16GB DDR4", ssd="SSD 1TB", board="B550 Motherboard",
                   psu="PSU 650W", case="yes")

    def test_unknown_spec_lines(self):
        self.check("""Mobo: Asrock unknown model
Videocard: 4gb
Processor: Intel
Price: 15k
Location: QC
Selling because upgrading na, smooth sa valorant""",
                   unknown=["Mobo: Asrock unknown model", "Videocard: 4gb", "Processor: Intel"])

    def test_emoji_bullets_all_caps(self):
        self.check("""✅ INTEL CORE I7 9700K
✅ RTX 2070 SUPER
✅ 2X8GB DDR4 3200MHZ
✅ CORSAIR CX650 PSU
✅ HYPER 212 COOLER
✅ NZXT H510 CASE
➡️ 500GB SSD""",
                   cpu="i7-9700K", gpu="RTX 2070 Super", ram="16GB DDR4", ssd="SSD 500GB", psu="PSU 650W", cooler="air",
                   case="yes")

    def test_8x2_ram_and_nvme_plus_hdd(self):
        self.check("Specs:\nRyzen 5 3600\nRam 16gb (8x2) 3200mhz\n1tb nvme + 1tb hdd\nGTX 1660 Ti",
                   cpu="Ryzen 3600", gpu="GTX 1660 Ti", ram="16GB DDR4", ssd="SSD 1TB")

    def test_generation_then_exact_model(self):
        self.check("i5 12th gen gaming pc\nCPU: Intel Core i5-12400F\nGPU: RTX 3060 (see below)\nGPU memory: RTX 3060 12gb",
                   cpu="i5-12400F", gpu="RTX 3060 12GB")

    def test_peripherals_full_setup(self):
        self.check("""Full set up with 27" monitor 144hz, RGB keyboard, mouse, headset, speakers, webcam, UPS
R5 5500 / RX 6600 / 16gb 3200mhz / 512gb ssd""",
                   cpu="Ryzen 5500", gpu="RX 6600", ram="16GB DDR4", ssd="SSD 512GB", monitor="Monitor 27in 144Hz",
                   peripherals=["headset", "keyboard", "mouse", "speaker", "ups", "webcam"])

    def test_swap_listing_with_chitchat(self):
        self.check("""FS/SWAP 🙏
Ryzen 3 3200G
8gb ram
Pm sakalam, no lowballers
Open for swap sa ps4""",
                   cpu="Ryzen 3200G", ram="8GB DDR4", check=["ram DDR guessed"])

    def test_cooler_fan_line_unknown(self):
        self.check("Ryzen 5 5600\nGPU: none\nFans: 3pcs rgb\nCasing: Inplay Meteor",
                   cpu="Ryzen 5600", case="Inplay Meteor", unknown=["Fans: 3pcs rgb"])

    def test_board_with_nzxt_case(self):
        self.check("MSI B550 tomahawk w/ NZXT H510 casing", board="B550 Motherboard", case="yes")

    def test_empty_and_weird(self):
        self.check("")
        self.check(None)
        self.check("💯💯💯\n\n|||+++")

    def test_not_included_negations(self):
        self.check("Ryzen 5 5600 / RX 6600 / 16gb ddr4 512gb ssd\nkeyboard and mouse not included\n24\" 144hz monitor (not included)",
                   cpu="Ryzen 5600", gpu="RX 6600", ram="16GB DDR4", ssd="SSD 512GB")
        self.check("Ryzen 5 5600G 16gb ddr4 512gb ssd\nwalang kasamang monitor at keyboard, may mouse",
                   cpu="Ryzen 5600G", ram="16GB DDR4", ssd="SSD 512GB", peripherals=["mouse"])
        self.check("Ryzen 5 5600G 16gb ddr4 512gb ssd\nHindi kasama ang 24 inch monitor", cpu="Ryzen 5600G", ram="16GB DDR4", ssd="SSD 512GB")

    def test_not_included_only_hits_its_own_words(self):
        self.check("GPU: RTX 3060 12GB box not included\nRAM 16GB DDR4 3200 rgb fans not included",
                   gpu="RTX 3060 12GB", ram="16GB DDR4")
        self.check("Ryzen 5 5600G, 16gb ddr4, 512gb ssd, A520M. Smooth valorant full settings 200fps",
                   cpu="Ryzen 5600G", ram="16GB DDR4", ssd="SSD 512GB", board="A520 Motherboard")

    def test_no_bottleneck_is_not_a_negation(self):
        self.check("Ryzen 5 5600 + RX 6600, no cpu bottleneck\n16gb ddr4 512gb ssd",
                   cpu="Ryzen 5600", gpu="RX 6600", ram="16GB DDR4", ssd="SSD 512GB")

    def test_brand_does_not_hide_generation_cpu(self):
        self.check("DELL OPTIPLEX 7000 i7 12TH GEN MINI PC\n16GB DDR4 256GB NVME/SSD SATA",
                   cpu="i7 12th Gen", ram="16GB DDR4", ssd="SSD 256GB", check=["cpu generation only"])

    def test_review_noise(self):
        self.check("FOR SALE: COMPLETE GAMING PC SETUP\nReason for selling: upgrade\nVideocard: 4gb\nVideocard: 4gb",
                   unknown=["Videocard: 4gb"], check=["set: monitor not itemized"])

    # real titles from data_dev.db
    def test_title_ryzen_rx6600(self):
        self.check("Ryzen 5 5600 + RX 6600 PC Unit (White Build)", cpu="Ryzen 5600", gpu="RX 6600")

    def test_title_rush_pc_unit_only(self):
        self.check("RUSH PC | Ryzen 5 5600GT | 16GB 3200MHz RAM | 500GB NVMe SSD (System Unit Only)",
                   cpu="Ryzen 5600GT", ram="16GB DDR4", ssd="SSD 500GB")

    def test_title_high_end(self):
        self.check("Gaming PC high-end SYSTEM UNIT RTX 4070 32GB RAM 1TB SSD i7 13700",
                   cpu="i7-13700", gpu="RTX 4070", ram="32GB DDR4", ssd="SSD 1TB", check=["ram DDR guessed"])


if __name__ == "__main__":
    unittest.main()
