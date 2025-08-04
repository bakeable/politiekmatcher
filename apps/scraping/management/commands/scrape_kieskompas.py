from django.core.management.base import BaseCommand
from apps.scraping.selenium_utils import get_driver
import time
from apps.content.models import (
    PoliticalParty,
    Theme,
    Statement,
    StatementPosition,
    ThemePosition,
)


class Command(BaseCommand):
    help = "Scrape stellingen en partij-antwoorden van StemWijzer"

    def cell_index_to_stance(self, cell_index):
        # 0 = strongly agree, 1 = agree, 2 = neutral, 3 = disagree, 4 = strongly disagree, 5 = no stance
        if cell_index == 0:
            return "strongly_agree"
        elif cell_index == 1:
            return "agree"
        elif cell_index == 2:
            return "neutral"
        elif cell_index == 3:
            return "disagree"
        elif cell_index == 4:
            return "strongly_disagree"
        else:
            return "neutral"

    def handle(self, *args, **kwargs):
        driver = get_driver()

        try:
            driver.get("https://tweedekamer2023.kieskompas.nl/nl/results/compass")
            time.sleep(1)  # wait for JS

            # Wait for and accept cookies
            try:
                continue_button = driver.find_element(
                    "xpath", "//button[contains(text(), 'Verder')]"
                )
                continue_button.click()
                time.sleep(1)
            except Exception as e:
                print(f"Fout bij accepteren cookies: {e}")

            #### SCRAPE THEME AND POSITIONS ####
            # Get the theme toggles
            theme_toggles = driver.find_elements("css selector", ".ThemeFilter .Toggle")
            themes = []
            for toggle_wrapper in theme_toggles:
                theme_name = toggle_wrapper.find_element(
                    "css selector", "label.Label"
                ).text.strip()
                if theme_name:
                    print(f"Found theme: {theme_name}")
                    themes.append(theme_name)

                # Disable the toggle
                toggle_input = toggle_wrapper.find_element(
                    "css selector", "input[type='checkbox']"
                )
                if toggle_input.is_selected():
                    toggle_input.click()
                    time.sleep(0.5)

            # Enable theme toggle one-by-one to scrape the position of each party on that theme
            for theme_name in themes:
                print(f"Enabling theme: {theme_name}")
                toggle_wrapper = driver.find_element(
                    "xpath", f"//label[contains(text(), '{theme_name}')]/.."
                )
                toggle_input = toggle_wrapper.find_element(
                    "css selector", "input[type='checkbox']"
                )
                if not toggle_input.is_selected():
                    toggle_input.click()
                    time.sleep(2)

                # Save the theme
                theme, _ = Theme.objects.update_or_create(
                    name=theme_name,
                    defaults={
                        "slug": theme_name.lower().replace(" ", "-"),
                        "source": "kieskompas",
                    },
                )
                print(f"Theme saved: {theme.name}")

                # Collect party positions for this theme
                party_positions = driver.find_elements(
                    "css selector", ".CompassParty svg title"
                )
                for party_position in party_positions:
                    text = party_position.get_attribute("innerHTML").strip()
                    if not text:
                        continue

                    # Text is formatted like: "Party name: 60% links, 88% progressief" or "Party name: 30% rechts, 45% conservatief"
                    party_name, remainder = text.split(":")
                    party_name = party_name.strip()
                    positions = remainder.split(",")
                    conservative, progressive, left, right = 0, 0, 0, 0
                    for position in positions:
                        percentage, ideology = position.strip().split("% ")
                        ideology = ideology.rstrip(".")
                        if ideology == "conservatief":
                            conservative = int(percentage)
                        elif ideology == "progressief":
                            progressive = int(percentage)
                        elif ideology == "links":
                            left = int(percentage)
                        elif ideology == "rechts":
                            right = int(percentage)

                    # Save the party position
                    print(
                        f"Saving position for {party_name}: "
                        f"conservative={conservative}, progressive={progressive}, "
                        f"left={left}, right={right}"
                    )
                    ThemePosition.objects.update_or_create(
                        theme=theme,
                        party=PoliticalParty.get_or_create(name=party_name),
                        defaults={
                            "conservative": conservative / 100,
                            "progressive": progressive / 100,
                            "left_wing": left / 100,
                            "right_wing": right / 100,
                            "source": "kieskompas",
                        },
                    )

                # Disable toggle
                if toggle_input.is_selected():
                    toggle_input.click()
                    time.sleep(0.5)

            ##### SCRAPE THEME AND STATEMENTS #####
            # Click the HeaderButton with tabindex=13 using CSS selector
            header_button = driver.find_element(
                "css selector", "a.HeaderButton[tabindex='13']"
            )
            header_button.click()
            time.sleep(1)

            # Find themes
            theme_options = driver.find_elements(
                "css selector", ".Select select option"
            )
            themes = []
            for option in theme_options:
                if option.get_attribute("value") == "":
                    continue

                theme_name = option.get_attribute("value").strip()
                if theme_name:
                    print(f"Found theme: {theme_name}")
                    themes.append(theme_name)

            # Loop through themes
            for theme_name in themes:
                print(f"Selecting theme: {theme_name}")
                select_element = driver.find_element("css selector", ".Select select")
                select_element.click()
                time.sleep(1)
                option_to_select = driver.find_element(
                    "xpath", f"//option[@value='{theme_name}']"
                )
                option_to_select.click()
                time.sleep(1)

                # Save the theme
                theme, _ = Theme.objects.update_or_create(
                    name=theme_name,
                    defaults={
                        "slug": theme_name.lower().replace(" ", "-"),
                        "source": "kieskompas",
                    },
                )

                # Find statements for the selected theme
                statement_buttons = driver.find_elements(
                    "css selector", "button.Statement"
                )
                for button in statement_buttons:
                    button.click()
                    time.sleep(0.2)
                    statement_text = button.find_element(
                        "css selector", "h1"
                    ).text.strip()
                    print(f"Found statement: {statement_text}")

                    # Save the statement
                    statement, _ = Statement.objects.update_or_create(
                        text=statement_text,
                        defaults={
                            "theme": theme,
                            "slug": statement_text.lower().replace(" ", "-")[:50],
                            "source": "kieskompas",
                        },
                    )
                    print(f"Statement saved")

                    # Loop through stances
                    stance_cells = driver.find_elements(
                        "css selector", "table tbody.JustificationTable__body tr td"
                    )

                    # 0 = strongly agree, 1 = agree, 2 = neutral, 3 = disagree, 4 = strongly disagree, 5 = no stance
                    cell_index = 0
                    for cell in stance_cells:
                        # Find parties in cell
                        party_buttons = cell.find_elements(
                            "css selector", ".CompassParty"
                        )

                        # Get aria-label from party elements
                        print(
                            f"Found {len(party_buttons)} parties in cell {cell_index}"
                        )
                        for party_button in party_buttons:
                            try:
                                party_svg = party_button.find_element(
                                    "css selector", "svg"
                                )
                            except Exception as e:
                                print(f"Error finding party SVG: {e}")
                                continue

                            # Find aria-label for the party
                            party_label = party_svg.get_attribute("aria-label")
                            if not party_label:
                                continue

                            party_name = party_label.strip()
                            print(f"Found party {cell_index}: {party_name}")

                            # Click the party button to reveal the stance
                            party_button.click()
                            time.sleep(0.1)

                            # Get the stance explanation
                            try:
                                explanation_element = driver.find_element(
                                    "css selector", ".JustificationTable__justification"
                                )
                                # Get all direct children of the explanation container and filter for h5 and p, preserving order
                                explanation_parts = []
                                for child in explanation_element.find_elements(
                                    "xpath", "./*"
                                ):
                                    tag_name = child.tag_name.lower()
                                    if tag_name in ("h5", "p"):
                                        text = child.text.strip()
                                        if (
                                            text
                                            and not "Bekijk de bron van de partij"
                                            in text
                                        ):
                                            explanation_parts.append(text)
                                explanation = "\n".join(explanation_parts)

                            except Exception as e:
                                print(f"Error finding explanation: {e}")
                                explanation = "Geen uitleg beschikbaar"

                            # Save the party's stance
                            StatementPosition.objects.update_or_create(
                                statement=statement,
                                party=PoliticalParty.get_or_create(name=party_name),
                                defaults={
                                    "stance": self.cell_index_to_stance(cell_index),
                                    "explanation": explanation,
                                    "source": "kieskompas",
                                },
                            )

                        # Increment cell index
                        cell_index += 1

            self.stdout.write(self.style.SUCCESS("✅ Scrape succesvol uitgevoerd"))

        finally:
            driver.quit()
