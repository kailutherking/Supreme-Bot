from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

from src.shared.models import MonitorQuery, ProductObservation


BASE_URL = "https://www.supremenewyork.com"
SHOP_PATH = "/shop/all/"


class SiteTimeoutError(RuntimeError):
    pass


class SiteDependencyError(RuntimeError):
    pass


class SupremeSite:
    site_id = "supreme"

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless

    def _create_driver(self, webdriver: Any, options_type: Any) -> Any:
        options = options_type()
        if self.headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        return driver

    def discover(self, query: MonitorQuery) -> tuple[ProductObservation, ...]:
        try:
            from selenium import webdriver
            from selenium.common.exceptions import (
                NoSuchElementException,
                TimeoutException,
            )
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as expected
            from selenium.webdriver.support.ui import WebDriverWait
        except ModuleNotFoundError as error:
            raise SiteDependencyError(
                "Selenium is required. Install project dependencies with "
                "'python -m pip install -r requirements.txt'."
            ) from error

        driver = self._create_driver(webdriver, Options)
        try:
            driver.set_page_load_timeout(30)
            try:
                driver.get(BASE_URL + SHOP_PATH)
                WebDriverWait(driver, 20).until(
                    expected.presence_of_element_located(
                        (By.CLASS_NAME, "inner-article")
                    )
                )
            except TimeoutException:
                raise SiteTimeoutError("Supreme listing page timed out.") from None

            products: dict[tuple[str, str | None], ProductObservation] = {}
            observed_at = datetime.now(timezone.utc)
            for card in driver.find_elements(By.CLASS_NAME, "inner-article"):
                try:
                    title = card.find_element(By.CLASS_NAME, "name").text.strip()
                    color = card.find_element(By.CLASS_NAME, "style").text.strip()
                    href = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                except NoSuchElementException:
                    continue
                if not title or not href:
                    continue

                product_url = urljoin(BASE_URL, href)
                parsed_url = urlsplit(product_url)
                if (
                    parsed_url.scheme != "https"
                    or parsed_url.hostname != "www.supremenewyork.com"
                ):
                    continue
                product_id = parsed_url.path.rstrip("/").rsplit("/", 1)[-1]
                if not product_id:
                    continue

                try:
                    image_url = card.find_element(By.TAG_NAME, "img").get_attribute("src")
                except NoSuchElementException:
                    image_url = None
                if image_url:
                    image_url = urljoin(BASE_URL, image_url)
                    if urlsplit(image_url).scheme != "https":
                        image_url = None

                product = ProductObservation(
                    site_id=self.site_id,
                    product_id=product_id,
                    title=title,
                    url=product_url,
                    observed_at=observed_at,
                    color=color or None,
                    image_url=image_url,
                    available=None,
                )
                if query.matches(product):
                    products[(product.product_id, product.variant_id)] = product
            return tuple(products.values())
        finally:
            driver.quit()
