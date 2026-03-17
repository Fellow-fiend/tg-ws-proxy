> [!CAUTION]
>
> ### Реакция антивирусов
> Windows Defender часто ошибочно помечает приложение как **Wacatac**.  
> Если вы не можете скачать из-за блокировки, то:
> 1) Попробуйте скачать версию win7 (она ничем не отличается в плане функционала)
> 2) Отключите антивирус на время скачивания, добавьте файл в исключения и включите обратно  
>
> **Всегда проверяйте, что скачиваете из интернета, тем более из непроверенных источников. Всегда лучше смотреть на детекты широко известных антивирусов на VirusTotal**

# TG WS Proxy

Локальный SOCKS5-прокси для Telegram Desktop, который перенаправляет трафик через WebSocket-соединения к указанным серверам, помогая частично ускорить работу Telegram.  
  
**Ожидаемый результат аналогичен прокидыванию hosts для Web Telegram**: ускорение загрузки и скачивания файлов, загрузки сообщений и части медиа.

<img width="529" height="487" alt="image" src="https://github.com/user-attachments/assets/6a4cf683-0df8-43af-86c1-0e8f08682b62" />

## Как это работает

```
Telegram Desktop → SOCKS5 (127.0.0.1:1080) → TG WS Proxy → WSS (kws*.web.telegram.org) → Telegram DC
```

1. Приложение поднимает локальный SOCKS5-прокси на `127.0.0.1:1080`
2. Перехватывает подключения к IP-адресам Telegram
3. Извлекает DC ID из MTProto obfuscation init-пакета
4. Устанавливает WebSocket (TLS) соединение к соответствующему DC через домены `kws{N}.web.telegram.org`
5. Если WS недоступен (302 redirect) — автоматически переключается на прямое TCP-соединение

## 🚀 Быстрый старт

### Windows
Перейдите на [страницу релизов](https://github.com/Flowseal/tg-ws-proxy/releases) и скачайте **`TgWsProxy.exe`**. Он собирается автоматически через [Github Actions](https://github.com/Flowseal/tg-ws-proxy/actions) из открытого исходного кода.

При первом запуске откроется окно с инструкцией по подключению Telegram Desktop. Приложение сворачивается в системный трей.

**Меню трея:**
- **Открыть в Telegram** — автоматически настроить прокси через `tg://socks` ссылку
- **Перезапустить прокси** — перезапуск без выхода из приложения
- **Настройки...** — GUI-редактор конфигурации
- **Открыть логи** — открыть файл логов
- **Выход** — остановить прокси и закрыть приложение


### Android (native APK, без root)
Теперь Android-версия делается как **нативное приложение на Python (Kivy)**, без Termux и без root.

- лёгкий GUI (host/port/DC + кнопки Start/Stop/Restart);
- прокси работает внутри приложения;
- используются порты > `1024`, поэтому root не нужен;
- для минимального расхода батареи оставляйте выключенным verbose.

#### Сборка APK
Требуется Linux/macOS с установленными Docker **или** Android build toolchain для Buildozer.

```bash
pip install --upgrade pip
pip install -r requirements-android.txt
buildozer android debug
```

После сборки APK лежит в:

```bash
bin/*.apk
```

#### Установка APK
1. Скопируйте `bin/tgwsproxy-0.1.0-arm64-v8a-debug.apk` (имя может отличаться) на телефон.
2. Разрешите установку из неизвестных источников.
3. Установите APK и запустите приложение **TG WS Proxy**.
4. В приложении нажмите **Start**.
5. В Telegram Android укажите SOCKS5:
   - Сервер: `127.0.0.1`
   - Порт: `1080` (или ваш в приложении)
   - Логин/пароль: пусто

## Установка из исходников

```bash
pip install -r requirements.txt
```

### Windows (Tray-приложение)

```bash
python windows.py
```

### Android (локальный запуск UI)

```bash
python main.py
```

### iOS (native app via Python/Kivy)

Добавлена iOS-версия на Python с простым легковесным GUI (`ios.py`):
- поля только для `host` и `port`;
- кнопки `Start/Stop/Restart`;
- редактирование DC отключено;
- автоматически используются **все доступные DC** из встроенной карты.

Локальный запуск интерфейса:

```bash
python ios.py
```

Сборка iOS в CI описана ниже (GitHub Actions).

### Консольный режим

```bash
python proxy/tg_ws_proxy.py [--port PORT] [--dc-ip DC:IP ...] [-v]
```

**Аргументы:**

| Аргумент | По умолчанию | Описание |
|---|---|---|
| `--port` | `1080` | Порт SOCKS5-прокси |
| `--dc-ip` | `2:149.154.167.220`, `4:149.154.167.220` | Целевой IP для DC (можно указать несколько раз) |
| `-v`, `--verbose` | выкл. | Подробное логирование (DEBUG) |

**Примеры:**

```bash
# Стандартный запуск
python proxy/tg_ws_proxy.py

# Другой порт и дополнительные DC
python proxy/tg_ws_proxy.py --port 9050 --dc-ip 1:149.154.175.205 --dc-ip 2:149.154.167.220

# С подробным логированием
python proxy/tg_ws_proxy.py -v
```

## Настройка Telegram Desktop

### Автоматически

ПКМ по иконке в трее → **«Открыть в Telegram»**

### Вручную

1. Telegram → **Настройки** → **Продвинутые настройки** → **Тип подключения** → **Прокси**
2. Добавить прокси:
   - **Тип:** SOCKS5
   - **Сервер:** `127.0.0.1`
   - **Порт:** `1080`
   - **Логин/Пароль:** оставить пустыми

## Конфигурация

Tray-приложение хранит данные в `%APPDATA%/TgWsProxy`:

```json
{
  "port": 1080,
  "dc_ip": [
    "2:149.154.167.220",
    "4:149.154.167.220"
  ],
  "verbose": false
}
```


### GitHub Actions

Добавлены workflow:

- `.github/workflows/android-apk-release.yml` — сборка Android APK.
- `.github/workflows/ios-pages-release.yml` — сборка Apple-артефактов (iPhone + macOS) и публикация страницы на GitHub Pages.

Для Apple workflow:
- запускается по тегам `v*` и вручную (`workflow_dispatch`);
- собирает `tgwsproxy.app` для iPhone (unsigned, требуется подпись для установки на устройство);
- собирает `tgwsproxy-macos.app` для macOS;
- публикует артефакты `tg-ws-proxy-iphone-app-unsigned`, `tg-ws-proxy-macos-app`;
- выкладывает страницу в GitHub Pages (`.github/pages/index.html`).

## Автоматическая сборка

Проект содержит спецификацию PyInstaller ([`windows.spec`](packaging/windows.spec)) для Windows-сборки и workflow для Android APK ([`.github/workflows/android-apk-release.yml`](.github/workflows/android-apk-release.yml)).

```bash
pip install pyinstaller
pyinstaller packaging/windows.spec
```

## Лицензия

[MIT License](LICENSE)
