import time
import csv
import json
import re
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

class ProfiFinalUltra:
    def __init__(self):
        print("🚀 Запуск парсера (Chrome 146)...")
        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        try:
            self.driver = uc.Chrome(options=options, version_main=146)
        except Exception as e:
            print(f"❌ Ошибка запуска: {e}")
            exit()

        self.all_data = []              # список словарей с данными мастеров
        self.seen_urls = set()          # для избежания дубликатов
        self.all_fieldnames = set()     # собираем все уникальные имена полей

    def clean_html(self, text):
        if not text:
            return ""
        soup = BeautifulSoup(str(text), 'html.parser')
        return soup.get_text(separator=' ', strip=True)

    def serialize_value(self, value):
        if value is None:
            return ""
        if isinstance(value, (bool, int, float, str)):
            return value
        return json.dumps(value, ensure_ascii=False)

    def extract_experience_and_years(self, info_list):
        """Извлекает стаж и годы на Профи из списка assembledInfoListing."""
        exp_total = "—"
        years_on_profi = "—"

        for item in info_list:
            content = item.get('content', '')
            if not content:
                continue

            clean = self.clean_html(content)

            match = re.search(r"На Профи\.ру с \d{4}", clean, re.IGNORECASE)
            if match:
                years_on_profi = match.group(0)
                continue

            match = re.search(r"На сервисе с \d{4}", clean, re.IGNORECASE)
            if match:
                years_on_profi = match.group(0)
                continue

            lines = clean.split('\n')
            for line in lines:
                if re.search(r"Опыт\s*(работы)?\s*[–—-]\s*.+", line, re.IGNORECASE):
                    if not re.search(r"Образование", line, re.IGNORECASE):
                        exp_total = re.sub(r"Опыт\s*(работы)?\s*[–—-]\s*", "", line, flags=re.IGNORECASE).strip()
                        break

        return exp_total, years_on_profi

    def parse_profile_page(self, url):
        """Заходит на страницу профиля и парсит текст по секциям"""
        try:
            self.driver.get(url)
            time.sleep(1.5)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            sections = {
                'О себе': '',
                'Образование': '',
                'Опыт': '',
                'Достижения': '',                
                'Дополнительная информация': '',
                'Выезд к клиенту': '',
                'Работает дистанционно': 'Нет',
                'Услуги и цены': ''
            }
            
            current_section = None
            stop_keywords = ['Фотографии', 'Документы и сертификаты', 'Отзывы', 
                           'Дополнительные услуги', 'Клиентам', 'Специалистам',
                           'Мобильная версия', 'Компания', 'Чат с поддержкой']
            
            for line in body_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                if line in sections:
                    current_section = line
                    continue
                elif line == 'Работает дистанционно':
                    sections['Работает дистанционно'] = 'Да'
                    continue
                elif current_section:
                    if line in sections:
                        current_section = line
                        continue
                    if line in stop_keywords:
                        current_section = None
                        continue
                    if sections[current_section]:
                        sections[current_section] += '\n' + line
                    else:
                        sections[current_section] = line
            
            for key in sections:
                if sections[key]:
                    sections[key] = re.sub(r'\n?Посмотреть все\n?.*', '', sections[key])
                    sections[key] = re.sub(r'\n?Показать ещё.*', '', sections[key])
                    sections[key] = re.sub(r'\n?Все услуги \d+.*', '', sections[key])
                    sections[key] = re.sub(r'\n?Оставить отзыв.*', '', sections[key])
            
            return sections
            
        except Exception as e:
            print(f"   ⚠️ Ошибка при парсинге профиля {url}: {e}")
            return {
                'О себе': '',
                'Образование': '',
                'Опыт': '',
                'Достижения': '',                # <-- добавлено
                'Дополнительная информация': '',
                'Выезд к клиенту': '',
                'Работает дистанционно': 'Нет',
                'Услуги и цены': ''
            }

    def parse_any_json(self, obj, parent_obj=None):
        count = 0
        if isinstance(obj, dict):
            alias = obj.get('id') or obj.get('alias')
            name_obj = obj.get('name')

            if alias and name_obj and isinstance(alias, str) and len(alias) > 5:
                name = name_obj.get('full') if isinstance(name_obj, dict) else name_obj
                if not name:
                    name = obj.get('fullName') or obj.get('shortName')

                is_specialist = (
                    obj.get('model') == 'SPECIALIST' or
                    bool(obj.get('fullName')) or
                    (isinstance(name_obj, dict) and 'full' in name_obj)
                )

                alias_is_digit_only = alias.isdigit()

                forbidden_keywords = ['установка', 'ремонт', 'монтаж', 'подключение']
                name_lower = name.lower() if name else ''
                has_forbidden = any(kw in name_lower for kw in forbidden_keywords)

                if (is_specialist and not alias_is_digit_only and not has_forbidden
                        and "profile" not in alias.lower()):
                    url = f"https://profi.ru/profile/{alias}/"
                    if url not in self.seen_urls:
                        row = {}
                        for key, val in obj.items():
                            row[key] = self.serialize_value(val)

                        info_list = obj.get('assembledInfoListing') or []
                        exp_total, years_on_profi = self.extract_experience_and_years(info_list)
                        row['_Стаж'] = exp_total
                        row['_Лет_на_сайте'] = years_on_profi
                        row['_Ссылка'] = url

                        self.all_data.append(row)
                        self.seen_urls.add(url)
                        self.all_fieldnames.update(row.keys())
                        count += 1

            for v in obj.values():
                if isinstance(v, (dict, list)):
                    count += self.parse_any_json(v, parent_obj=obj)

        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    count += self.parse_any_json(item, parent_obj=None)
        return count

    def get_data_from_page_source(self):
        try:
            raw_data = self.driver.execute_script("return JSON.stringify(window.__NEXT_DATA__)")
            if raw_data:
                data = json.loads(raw_data)
                return self.parse_any_json(data)
        except:
            return 0
        return 0

    def find_masters_in_logs(self):
        try:
            logs = self.driver.get_log('performance')
        except:
            return 0

        found_in_step = 0
        for entry in logs:
            try:
                message = json.loads(entry['message'])['message']
                if message['method'] == 'Network.responseReceived':
                    url = message['params']['response']['url']
                    if "graphql" in url or "api" in url:
                        request_id = message['params']['requestId']
                        body = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                        content = json.loads(body['body'])
                        found_in_step += self.parse_any_json(content)
            except:
                continue
        return found_in_step

    def run(self):
        url0 = "https://profi.ru/cabinet/order/89150907/?tabName=PROFILES"
        self.driver.get(url0)
        time.sleep(5)

        print("\n✅ Страница открыта.")
        print("1. Авторизуйтесь вручную (телефон + СМС)")
        print("2. Пролистайте список вниз, нажимайте 'Показать ещё' пока не загрузятся все мастера")
        print("3. После завершения нажмите ENTER в консоли...")
        input()

        print("⏳ Этап 1: Сбор технических данных (JSON + логи)...")
        n1 = self.get_data_from_page_source()
        n2 = self.find_masters_in_logs()
        print(f"   Найдено профилей: {len(self.all_data)}")

        print(f"\n⏳ Этап 2: Парсинг страниц профилей...")
        for i, row in enumerate(self.all_data, 1):
            url = row.get('_Ссылка', '')
            if not url:
                continue
            name = row.get('fullName') or row.get('shortName') or url
            print(f"   [{i}/{len(self.all_data)}] 🔍 {name}")
            info = self.parse_profile_page(url)
            row['О себе'] = info.get('О себе', '')
            row['Образование'] = info.get('Образование', '')
            row['Опыт'] = info.get('Опыт', '')
            row['Достижения'] = info.get('Достижения', '')
            row['Дополнительная информация'] = info.get('Дополнительная информация', '')
            row['Выезд к клиенту'] = info.get('Выезд к клиенту', '')
            row['Работает дистанционно'] = info.get('Работает дистанционно', 'Нет')
            row['Услуги и цены'] = info.get('Услуги и цены', '')
            self.all_fieldnames.update(row.keys())

        print(f"✨ Всего спарсено профилей: {len(self.all_data)}")
        self.save()

    def save(self):
        if not self.all_data:
            print("📭 Данные отсутствуют.")
            return

        fieldnames = sorted(self.all_fieldnames)
        filename = "moskva_tennis_women_all.csv"
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.all_data:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

        print(f"🏁 Файл сохранен: {filename}")

if __name__ == "__main__":
    parser = ProfiFinalUltra()
    try:
        parser.run()
    except KeyboardInterrupt:
        print("\nПрервано.")
    finally:
        parser.driver.quit()