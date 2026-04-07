import { createBoard, getBoards } from '@/features/boards/api/boards';
import { createCard, getCards } from '@/features/cards/api/cards';
import { createColumn, getColumns } from '@/features/columns/api/columns';
import { createWorkspace, getWorkspaces } from '@/features/workspaces/api/workspaces';
import type { BoardColumn, Card } from '@/shared/types/api';

const ROADMAP_WORKSPACE_NAME = 'P2P Planner roadmap';
const ROADMAP_BOARD_NAME = 'План работ по проекту';

const ROADMAP_COLUMNS = [
  {
    name: 'Готово',
    description: 'То, что уже реализовано и проверено в текущем проекте.',
  },
  {
    name: 'Сейчас',
    description: 'Ближайшие правки и активные задачи.',
  },
  {
    name: 'Далее',
    description: 'Следующие инженерные этапы после текущего полиша.',
  },
  {
    name: 'Потом',
    description: 'То, что важно, но идет после core sync и стабилизации.',
  },
] as const;

const ROADMAP_CARDS = {
  'Готово': [
    'MVP scope v1',
    'Docs v2 и ADR',
    'Data model и БД',
    'Backend module map',
    'OpenAPI / HTTP API v1',
    'Auth и identity модель',
    'Migrations и backend skeleton',
    'Core backend CRUD',
    'Appearance / customization backend',
    'Activity / history / audit',
    'Web frontend architecture',
    'Web frontend core UI',
    'Web customization UI',
    'UI cleanup и рефакторинг beta-базы',
  ],
  'Сейчас': [
    'Косметический polish кнопок и micro-UX',
    'Автогенерация dev-roadmap board',
  ],
  'Далее': [
    'Local-first слой',
    'Sync model implementation plan',
    'Conflict resolution',
    'P2P / relay / bootstrap abstraction',
    'Integrations architecture',
    'Import / export / backup',
  ],
  'Потом': [
    'Security / privacy / threat model',
    'Testing strategy',
    'Deployment / packaging',
    'Beta scope',
    'Mobile architecture',
  ],
} as const satisfies Record<string, readonly string[]>;

function buildCardDescription(columnName: string, title: string) {
  if (columnName === 'Готово') {
    return `Этап «${title}» уже закрыт и может служить опорой для следующих шагов.`;
  }
  if (columnName === 'Сейчас') {
    return `Актуальная небольшая задача для текущего витка разработки: ${title}.`;
  }
  if (columnName === 'Далее') {
    return `Следующий логичный этап после текущего полиша интерфейса: ${title}.`;
  }
  return `Отложенная, но запланированная тема: ${title}.`;
}

async function ensureRoadmapWorkspace() {
  const workspaces = await getWorkspaces();
  const existing = workspaces.items.find((item) => !item.isArchived && item.name === ROADMAP_WORKSPACE_NAME);

  if (existing) return existing;

  return createWorkspace({
    name: ROADMAP_WORKSPACE_NAME,
    visibility: 'private',
    description: 'Автогенерируемый dev-workspace с примерной доской по текущему проекту.',
  });
}

async function ensureRoadmapBoard(workspaceId: string) {
  const boards = await getBoards(workspaceId);
  const existing = boards.items.find((item) => !item.isArchived && item.name === ROADMAP_BOARD_NAME);

  if (existing) return existing;

  return createBoard(workspaceId, {
    name: ROADMAP_BOARD_NAME,
    description: 'Наглядная дорожная карта разработки прямо внутри самого planner-проекта.',
  });
}

async function ensureColumns(boardId: string) {
  let columns = await getColumns(boardId);

  for (const columnSeed of ROADMAP_COLUMNS) {
    const exists = columns.items.some((item) => item.name === columnSeed.name);
    if (!exists) {
      await createColumn(boardId, {
        name: columnSeed.name,
        description: columnSeed.description,
      });
      columns = await getColumns(boardId);
    }
  }

  return columns.items;
}

async function ensureCards(boardId: string, columns: BoardColumn[]) {
  const cards = await getCards(boardId);
  const existingByColumn = new Map<string, Card[]>();

  cards.items.forEach((card) => {
    const items = existingByColumn.get(card.columnId) || [];
    items.push(card);
    existingByColumn.set(card.columnId, items);
  });

  const columnByName = new Map(columns.map((column) => [column.name, column]));

  for (const [columnName, titles] of Object.entries(ROADMAP_CARDS)) {
    const column = columnByName.get(columnName);
    if (!column) continue;

    const existingCards = existingByColumn.get(column.id) || [];

    for (const title of titles) {
      const exists = existingCards.some((card) => card.title === title);
      if (exists) continue;

      const created = await createCard(boardId, {
        title,
        description: buildCardDescription(columnName, title),
        columnId: column.id,
      });
      existingCards.push(created);
      existingByColumn.set(column.id, existingCards);
    }
  }
}

export async function ensureProjectRoadmapSeed() {
  const workspace = await ensureRoadmapWorkspace();
  const board = await ensureRoadmapBoard(workspace.id);
  const columns = await ensureColumns(board.id);
  await ensureCards(board.id, columns);

  return {
    workspaceId: workspace.id,
    boardId: board.id,
  };
}
