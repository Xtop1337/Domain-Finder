## Domain Finder
Domain Finder — это кроссплатформенное приложение с графическим интерфейсом для быстрого поиска доменов и перечисления поддоменов (subdomain enumeration). 
Инструмент принимает на вход ключевое слово (название бренда,сайта) или базовый домен, а затем собирает связанные поддомены, используя публичные API.

 ## ✨ Возможности
* **Поиск по домену**: Поддерживает прямой ввод доменов (например, `example.com`).
* **Интеграция с API**: 
  * `crt.sh` (поиск по сертификатам Transparency Logs).
  * `HackerTarget` (Host Search API).
* **Удобный GUI**: Интерфейс написан на [Flet](https://flet.dev/) с поддержкой темной и светлой темы, логами в реальном времени и индикатором прогресса.
* **Экспорт данных**: Найденные уникальные домены можно скопировать в буфер обмена одной кнопкой или сохранить в формате `.json` в папку `results/`.

## 📁 Структура проекта

* `app.py` — Точка входа в приложение. Содержит логику графического интерфейса (UI) на базе Flet.
* `core.py` — Ядро приложения. Отвечает за HTTP-запросы к API, фильтрацию невалидных доменов и сохранение результатов.
* `known_sites.json` — Локальная база данных (словарь), связывающая ключевые слова с их реальными доменами. Вы можете добавлять туда свои сервисы.
* `requirements.txt` — Список зависимостей Python, необходимых для работы утилиты.

## 🚀 Установка и запуск

1. **Предварительные требования**: Убедитесь, что у вас установлен Python версии 3.8 или выше.
2. **Клонирование/Скачивание**: Скачайте проект в удобную для вас директорию.
3. **Установка зависимостей**: 
   Откройте терминал в папке с проектом и выполните команду:
   ```bash
   pip install -r requirements.txt
   ```
4. **Запуск**:
   ```bash
   python app.py
   ```




## Domain Finder

**Domain Finder** is a cross-platform application with a graphical interface for fast domain discovery and subdomain enumeration.
The tool accepts a keyword (e.g., a brand or website name) or a base domain as input, then collects related subdomains using public APIs.

---

## ✨ Features

* **Domain search**: Supports direct domain input (e.g., `example.com`).
* **API integration**:

  * `crt.sh` (certificate search via Transparency Logs)
  * `HackerTarget` (Host Search API)
* **User-friendly GUI**: Built with [Flet](https://flet.dev/), featuring dark/light themes, real-time logs, and a progress indicator.
* **Data export**: Discovered unique domains can be copied to the clipboard with one click or saved as `.json` files in the `results/` directory.

---

## 📁 Project Structure

* `app.py` — Application entry point. Contains the graphical user interface (UI) logic built with Flet.
* `core.py` — Core logic. Handles API requests, filters invalid domains, and saves results.
* `known_sites.json` — Local database (dictionary) mapping keywords to real domains. You can extend it with your own services.
* `requirements.txt` — List of Python dependencies required to run the application.

---

## 🚀 Installation & Usage

1. **Prerequisites**: Make sure you have Python 3.8 or higher installed.

2. **Clone / Download**: Download or clone the repository to your preferred directory.

3. **Install dependencies**:
   Open a terminal in the project folder and run:

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:

   ```bash
   python app.py
   ```

## Сборка EXE

Сборка выполняется на Windows из корня репозитория. Установите зависимости для
разработки и запустите PyInstaller:

```powershell
py -m pip install -r requirements-dev.txt
py -m PyInstaller --noconfirm --clean Domain-Finder.spec
```

Конфигурация собирает точку входа `app.py` в оконное приложение без консоли,
включает `known_sites.json` в пакет и задаёт имя исполняемого файла
`Domain-Finder`. Готовый файл находится по пути
`dist\Domain-Finder.exe`.
