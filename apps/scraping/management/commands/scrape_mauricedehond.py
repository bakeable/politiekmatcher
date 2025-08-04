from datetime import datetime
from django.core.management.base import BaseCommand
from apps.scraping.selenium_utils import get_driver
import time
from politiekmatcher.settings import PARTY_NAME_MAPPINGS


class Command(BaseCommand):
    help = "Scrape de laatste peilingen van Maurice de Hond"

    def handle(self, *args, **kwargs):
        driver = get_driver()
        try:
            driver.get("https://home.noties.nl/peil/")
            time.sleep(2)

            def find_and_click_stemming_button(driver, depth=0):
                print(f"{'  ' * depth}📄 Searching at depth {depth}")
                if depth > 5:
                    print("⚠️ Max iframe depth reached")
                    return False

                try:
                    print(f"{'  ' * depth}🔍 Current URL: {driver.current_url}")
                    iframes = driver.find_elements("tag name", "iframe")
                    print(
                        f"{'  ' * depth}Found {len(iframes)} iframes at depth {depth}"
                    )
                    for i, iframe in enumerate(iframes):
                        print(
                            f"{'  ' * depth}Iframe {i}: {iframe.get_attribute('src')}"
                        )
                        driver.switch_to.frame(iframe)
                        time.sleep(1)

                        # Try to find the button
                        buttons = driver.find_elements("css selector", ".button")
                        print(f"{'  ' * depth}Found {len(buttons)} buttons")
                        for j, button in enumerate(buttons):
                            print(
                                f"{'  ' * depth}Button {j}: text='{button.text}' class='{button.get_attribute('class')}'"
                            )
                            if "De Stemming" in button.text:
                                print(
                                    f"{'  ' * depth}✅ Found 'De Stemming' button, clicking..."
                                )
                                button.click()
                                return True

                        # Recurse deeper
                        if find_and_click_stemming_button(driver, depth + 1):
                            return True

                        # Go back out of iframe if nothing found
                        driver.switch_to.parent_frame()

                except Exception as e:
                    print(f"{'  ' * depth}⚠️ Error while traversing iframes: {e}")
                    driver.switch_to.parent_frame()

                return False

            if not find_and_click_stemming_button(driver):
                self.stdout.write(self.style.ERROR("Knop 'De Stemming' niet gevonden"))
                return

            time.sleep(3)

            # Extract party names and seat counts
            from collections import defaultdict

            party_seats = defaultdict()

            party_groups = driver.find_elements("css selector", ".party-group")
            print(f"🔍 Found {len(party_groups)} party groups")

            for group in party_groups:
                party_name = group.get_attribute("data-party")
                circles = group.find_elements("css selector", "circle")
                seat_count = len(circles)
                print(f"🟠 {party_name}: {seat_count} zetels")
                if len(party_name) > 0 and len(circles) > 0:
                    # Get the color from the 'fill' attribute of the first circle
                    fill_color = circles[0].get_attribute("fill")
                    print(f"  - Kleur: {fill_color}")
                else:
                    fill_color = "rgb(0, 0, 0)"  # Default color if not found

                party_seats[party_name] = {"seats": seat_count, "color": fill_color}

            self.stdout.write(
                self.style.SUCCESS(f"✅ {len(party_seats)} partijen gevonden")
            )

        finally:
            driver.quit()

        # Get all parties from the database
        from apps.content.models import PoliticalParty, ParliamentarySeats

        for party_name, data in party_seats.items():
            # Normalize party name using mappings
            party = PoliticalParty.get_or_create(party_name)
            print(f"🔵 Verwerken partij: {party.name}")

            # Find or create the party
            ParliamentarySeats.objects.update_or_create(
                party=party,
                date=datetime.now().date().isoformat(),
                year=datetime.now().year,
                defaults={"seats": data["seats"], "source": "mauricedehond"},
            )

            print(
                f"🟢 Zetels voor {party.name} bijgewerkt: {data['seats']}, kleur: {data['color']}"
            )
            # If color is rgb, convert to hex
            if data["color"].startswith("rgb"):
                rgb = tuple(map(int, data["color"][4:-1].split(",")))
                hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
                party.color_hex = hex_color
                print(f"  - Kleur omgezet naar hex: {hex_color}")
            else:
                # Assume it's already a hex color
                if data["color"].startswith("#"):
                    data["color"] = data["color"].lstrip("#")

                # Update the party color
                party.color_hex = data["color"]

            # Save the party with the new color
            party.save()

            print(f"🟡 Partij {party.name} bijgewerkt")
