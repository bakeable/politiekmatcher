from django.core.management.base import BaseCommand
from apps.scraping.selenium_utils import get_driver
import time
from apps.content.models import (
    PoliticalParty,
    Theme,
    Statement,
    StatementPosition,
)


class Command(BaseCommand):
    help = "Scrape stellingen en partij-antwoorden van StemWijzer"

    def handle(self, *args, **kwargs):
        all_statements = []

        driver = get_driver()
        try:
            driver.get("https://tweedekamer2023.stemwijzer.nl/")
            time.sleep(2)  # wait for JS

            # Wait for and accept cookies
            try:
                accept_button = driver.find_element(
                    "xpath", "//button[contains(text(), 'Akkoord')]"
                )
                accept_button.click()
                time.sleep(1)
            except Exception as e:
                print(f"Fout bij accepteren cookies: {e}")

            # Start StemWijzer
            start_button = driver.find_element(
                "xpath", "//button[contains(text(), 'Start')]"
            )
            start_button.click()
            time.sleep(2)

            for i in range(31):
                try:
                    theme_el = driver.find_element("css selector", ".statement__theme")
                    theme_text = theme_el.text.strip()

                    statement_el = driver.find_element("css selector", ".statement h1")
                    statement_text = statement_el.text.strip()

                    # Click statement info button
                    info_button = driver.find_element(
                        "css selector", ".statement__tab-button--more-info"
                    )
                    info_button.click()
                    time.sleep(2)

                    try:
                        # Get the statement explanation
                        explanation_el = driver.find_element(
                            "css selector", ".statement__tab-text"
                        )
                        explanation_text = explanation_el.text.strip()
                    except Exception as e:
                        explanation_text = "Geen uitleg beschikbaar"

                    print(
                        f"Stelling {i+1}: {statement_text} - Thema: {theme_text} - Uitleg: {explanation_text}"
                    )

                    # Click statement tab button
                    statement_tab = driver.find_element(
                        "css selector", ".statement__tab-button--parties"
                    )
                    statement_tab.click()
                    time.sleep(2)

                    # Loop through columns (0 = agree, 1 = neutral, 2 = disagree)
                    parties_columns = driver.find_elements(
                        "css selector", ".statement__parties-column.parties-column"
                    )
                    statements = []
                    for column in parties_columns:
                        # Find parties in column
                        party_sections = column.find_elements(
                            "css selector", ".parties-column__party"
                        )
                        for party_section in party_sections:
                            # Within party, find button to reveal positions
                            party_button = party_section.find_element(
                                "css selector", "button"
                            )
                            # Scroll into view and click the button
                            driver.execute_script(
                                "arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});",
                                party_button,
                            )
                            time.sleep(0.5)
                            party_button.click()
                            time.sleep(0.5)

                            # Get the party logo url and position
                            party_logo = party_section.find_element(
                                "css selector", "button img"
                            )
                            party_logo_url = party_logo.get_attribute("src")
                            raw_style = party_logo.get_attribute("style") or ""
                            party_logo_position = ""
                            for rule in raw_style.split(";"):
                                if "object-position" in rule:
                                    party_logo_position = rule.split(":")[1].strip()
                                    break

                            # Get the dive content with party position
                            explanation_div = party_section.find_element(
                                "css selector", "div"
                            )
                            explanation = explanation_div.text.strip()
                            party_name = party_button.text.strip()
                            statements.append(
                                {
                                    "theme": theme_text,
                                    "statement": statement_text,
                                    "statement_explanation": explanation_text,
                                    "party_logo_url": party_logo_url,
                                    "party_logo_object_position": party_logo_position,
                                    "party": party_name,
                                    "explanation": explanation,
                                    "agree": column == parties_columns[0],
                                    "disagree": column == parties_columns[2],
                                }
                            )

                            print(
                                f"Partij: {party_name} - Positie: {'Akkoord' if column == parties_columns[0] else 'Neutraal' if column == parties_columns[1] else 'Niet akkoord'}"
                            )

                    # Save the statement data
                    for statement_data in statements:
                        all_statements.append(statement_data)
                        theme, _ = Theme.objects.update_or_create(
                            name=statement_data["theme"],
                            defaults={"source": "stemwijzer"},
                        )
                        print(f"Theme: {theme.name}")
                        statement, _ = Statement.objects.update_or_create(
                            theme=theme,
                            text=statement_data["statement"],
                            defaults={
                                "explanation": statement_data["statement_explanation"],
                                "source": "stemwijzer",
                            },
                        )
                        print(f"Statement: {statement.text}")
                        party = PoliticalParty.get_or_create(
                            name=statement_data["party"],
                            logo_url=statement_data["party_logo_url"],
                            logo_object_position=statement_data[
                                "party_logo_object_position"
                            ],
                        )
                        print(f"Party: {party.name} - Logo URL: {party.logo_url}")
                        StatementPosition.objects.update_or_create(
                            statement=statement,
                            party=party,
                            stance=(
                                "agree"
                                if statement_data["agree"]
                                else (
                                    "disagree"
                                    if statement_data["disagree"]
                                    else "neutral"
                                )
                            ),
                            explanation=statement_data["explanation"],
                            defaults={
                                "source": "stemwijzer",
                            },
                        )
                        print(
                            f"Position: {statement_data['explanation']} - Stance: {'Agree' if statement_data['agree'] else 'Disagree' if statement_data['disagree'] else 'Neutral'}"
                        )

                    # Klik op Volgende
                    next_btn = driver.find_element("css selector", ".statement__skip")
                    next_btn.click()
                    time.sleep(1)
                except Exception as e:
                    print(f"Fout bij stelling {i+1}: {e}")
                    continue

            self.stdout.write(self.style.SUCCESS("✅ Scrape succesvol uitgevoerd"))

        finally:
            driver.quit()
