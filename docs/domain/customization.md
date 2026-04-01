# Кастомизация и универсализация

## Цель

Кастомизация в этом проекте должна давать **реальную пользовательскую ценность**,
но не превращать v1 в редактор тем и ассетов. Поэтому для этого этапа мы
фиксируем **узкий, но рабочий customization slice**:
- пользовательская тема приложения;
- board appearance settings;
- preset-based wallpapers без файловых загрузок;
- явная граница между пользовательскими предпочтениями и общими настройками доски.

## Что теперь реально входит в v1

В пределах этого этапа v1 поддерживает:
1. `UserAppearancePreferences` для текущего пользователя:
   - `app_theme`: `system | light | dark`;
   - `density`: `comfortable | compact`;
   - `reduce_motion`.
2. `BoardAppearanceSettings` для доски:
   - `theme_preset` как строковый preset id;
   - `wallpaper` вида `none | solid | gradient | preset`;
   - `column_density`;
   - `card_preview_mode`;
   - флаги отображения описания, дат и прогресса чеклистов;
   - `custom_properties` как ограниченный JSON-объект для future-ready расширения.
3. Чтение дефолтных настроек даже если кастомная запись еще не создана.
4. Отдельный API surface для `me/appearance` и `boards/{boardId}/appearance`.

## Что сознательно не входит даже после этого этапа

По-прежнему не входят в v1:
- загрузка пользовательских изображений для обоев;
- хранение файловых/asset wallpapers;
- визуальный конструктор палитр и design tokens;
- workspace-level inheritance UI;
- per-column style presets;
- custom CSS / arbitrary theme packs;
- импорт/экспорт тем.

## Границы модели

### 1. Пользовательские предпочтения != board state
`UserAppearancePreferences` относятся к персональному UX пользователя и не
меняют данные других участников workspace.

### 2. Board appearance — shared state
`BoardAppearanceSettings` принадлежат доске и влияют на то, как доска должна
рендериться для всех участников, если клиент уважает эти настройки.

### 3. Preset ids лучше, чем захардкоженные палитры в БД
Backend хранит **идентификатор пресета**, а не полный набор CSS-токенов. Это:
- уменьшает жесткость схемы;
- дает frontend свободу эволюции;
- не мешает позже перейти к richer theme registry.

### 4. Wallpapers в v1 не равны файлам
Пока у нас нет обязательного attachments/assets слоя, обои описываются как
конфигурация вида `kind + value`, а не как ссылка на загруженный файл.

### 5. Future-ready расширение идет через ограниченный JSON-object
`custom_properties` допускается только как JSON object, чтобы:
- не смешивать кастомизацию с произвольным blob;
- оставлять пространство для флагов и будущих UI-настроек;
- не плодить миграции на каждый мелкий эксперимент.

## Правила доступа

### User appearance preferences
- читает и меняет только сам пользователь.

### Board appearance settings
- читать могут все участники workspace, у которых есть доступ к board;
- менять могут только `owner` и `admin`, так как это shared board-level state.

## Инварианты

1. `app_theme` ограничен `system | light | dark`.
2. `density` и `column_density` ограничены `comfortable | compact`.
3. `card_preview_mode` ограничен `compact | expanded`.
4. `wallpaper.kind` ограничен `none | solid | gradient | preset`.
5. Если `wallpaper.kind = none`, то `wallpaper.value = null`.
6. Если `wallpaper.kind != none`, то `wallpaper.value` обязателен.
7. `custom_properties` должен быть JSON object.

## Направления расширения

В будущем поверх этой базы можно добавить:
- workspace defaults для новых boards;
- theme registry с версионируемыми preset packs;
- image wallpapers через отдельный assets/attachments слой;
- per-user overrides поверх board appearance;
- branded workspace themes;
- доступность и контраст как отдельный поднабор appearance policy.
