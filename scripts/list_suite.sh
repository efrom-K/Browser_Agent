#!/bin/zsh
# "Find the N best ..." tasks across sites, one auto_run each (logs in runs/<name>/).
# Avito snapshot task needs: (cd runs/avito_snap && python3 -m http.server 8765 --bind 127.0.0.1)
cd "$(dirname "$0")/.."
run() { echo "=== $1 $(date +%T)"; .venv/bin/python -u scripts/auto_run.py "$1" "$2" --headless --max-steps 40 --max-minutes 15 2>&1 | grep -E '"status"|"success"|"steps"|"minutes"|"reason"'; }
run hn "Найди на https://news.ycombinator.com 5 самых обсуждаемых историй на первых двух страницах."
run ws "На сайте https://webscraper.io/test-sites/e-commerce/static найди 5 лучших ноутбуков. Сам реши, что значит «лучших»."
run gh "Найди на https://github.com 5 лучших репозиториев с браузерными AI-агентами на Python. Сам реши, что значит «лучших»."
run openlib "Найди на https://openlibrary.org 5 лучших книг про машинное обучение. Сам реши, что значит «лучших»."
run wiki "Найди в английской Википедии (https://en.wikipedia.org) 5 самых высоких зданий в Европе и их высоту."
run books "На https://books.toscrape.com найди 5 самых дешёвых книг в категории Travel."
run cl "Найди на craigslist в Нью-Йорке 10 лучших объявлений iPhone 15. Сам реши, что значит «лучших»."
run avito_snap "Это выдача Авито по iPhone 16 в Москве: http://127.0.0.1:8765/p1.html — найди на ней 10 лучших объявлений. Сам реши, что значит «лучших». Для каждого дай название, цену, продавца и ссылку."
echo "=== SUITE DONE $(date +%T)"
