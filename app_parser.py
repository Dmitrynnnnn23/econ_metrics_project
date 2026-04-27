import time
import csv
import json
import re
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

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
        """
        Преобразует значение любого типа в примитив для CSV.
        - None → ""
        - bool, int, float, str → как есть (str для bool)
        - dict, list → JSON-строка
        """
        if value is None:
            return ""
        if isinstance(value, (bool, int, float, str)):
            return value
        # для сложных типов — сериализуем в JSON
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

            # Поиск "На Профи.ру с ..."
            match = re.search(r"На Профи\.ру с \d{4}", clean, re.IGNORECASE)
            if match:
                years_on_profi = match.group(0)
                continue

            # Поиск "На сервисе с ..."
            match = re.search(r"На сервисе с \d{4}", clean, re.IGNORECASE)
            if match:
                years_on_profi = match.group(0)
                continue

            # Поиск опыта работы (исключая блоки образования)
            lines = clean.split('\n')
            for line in lines:
                if re.search(r"Опыт\s*(работы)?\s*[–—-]\s*.+", line, re.IGNORECASE):
                    if not re.search(r"Образование", line, re.IGNORECASE):
                        exp_total = re.sub(r"Опыт\s*(работы)?\s*[–—-]\s*", "", line, flags=re.IGNORECASE).strip()
                        break

        return exp_total, years_on_profi

    def parse_any_json(self, obj, parent_obj=None):
        count = 0
        if isinstance(obj, dict):
            alias = obj.get('id') or obj.get('alias')
            name_obj = obj.get('name')

            if alias and name_obj and isinstance(alias, str) and len(alias) > 5:
                # Определяем имя мастера
                name = name_obj.get('full') if isinstance(name_obj, dict) else name_obj
                if not name:
                    name = obj.get('fullName') or obj.get('shortName')

                # Дополнительные проверки, что это профиль мастера, а не категория услуги
                is_specialist = (
                    obj.get('model') == 'SPECIALIST' or
                    bool(obj.get('fullName')) or
                    (isinstance(name_obj, dict) and 'full' in name_obj)
                )

                # Исключаем полностью цифровые alias (часто категории услуг)
                alias_is_digit_only = alias.isdigit()

                # Исключаем ключевые слова категорий в названии
                forbidden_keywords = ['установка', 'ремонт', 'монтаж', 'подключение']
                name_lower = name.lower() if name else ''
                has_forbidden = any(kw in name_lower for kw in forbidden_keywords)

                # Основная проверка на профиль мастера
                if (is_specialist and not alias_is_digit_only and not has_forbidden
                        and "profile" not in alias.lower()):
                    url = f"https://profi.ru/profile/{alias}/"
                    if url not in self.seen_urls:
                        # Собираем ВСЕ поля из объекта мастера
                        row = {}
                        for key, val in obj.items():
                            row[key] = self.serialize_value(val)

                        # Добавляем вычисляемые поля
                        info_list = obj.get('assembledInfoListing') or []
                        exp_total, years_on_profi = self.extract_experience_and_years(info_list)
                        row['_Стаж'] = exp_total
                        row['_Лет_на_сайте'] = years_on_profi
                        row['_Ссылка'] = url

                        self.all_data.append(row)
                        self.seen_urls.add(url)
                        self.all_fieldnames.update(row.keys())
                        count += 1

            # Рекурсивно обходим значения
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
        url = "https://profi.ru/remont/electromontajnye-raboty/ustanovka-rozetok-i-vyklyuchatelei/?seamless=1&tabName=PROFILES"
        self.driver.get(url)
        time.sleep(5)

        print("\n✅ Страница открыта.")
        print("1. Пролистайте список вниз, чтобы подгрузить всех нужных мастеров.")
        print("2. После завершения прокрутки нажмите ENTER в консоли...")
        input()

        print("⏳ Извлечение данных...")
        self.get_data_from_page_source()
        self.find_masters_in_logs()

        print(f"✨ Найдено профилей: {len(self.all_data)}")
        self.save()

    def save(self):
        if not self.all_data:
            print("📭 Данные отсутствуют.")
            return

        # Превращаем набор полей в список, сортируем для предсказуемости
        fieldnames = sorted(self.all_fieldnames)

        filename = "profi_masters_all_fields_new.csv"
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            # Для каждой записи дописываем отсутствующие поля пустыми строками
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