import fixture from '@/test/fixtures/board-backup-v1.json';
import {
  BoardBundleValidationError,
  chooseImportedBoardName,
  parseBoardBundleText,
} from '@/features/integrations/lib/boardBundle';

function cloneFixture() {
  return structuredClone(fixture) as unknown as Record<string, any>;
}

describe('board bundle parser', () => {
  it('parses the current board backup format and builds a safe preview', () => {
    const preview = parseBoardBundleText(JSON.stringify(fixture), 'fixture.json');

    expect(preview.board.name).toBe('Release plan');
    expect(preview.counts).toEqual({
      columns: 2,
      cards: 2,
      labels: 1,
      checklists: 1,
      checklistItems: 1,
      comments: 1,
    });
    expect(preview.cards[1]).toMatchObject({
      id: 'card-child',
      parentCardId: 'card-parent',
      status: 'completed',
      isArchived: true,
    });
    expect(preview.appearance).toMatchObject({
      themePreset: 'plum-ink',
      wallpaper: { kind: 'preset', value: 'aurora' },
    });
    expect(preview.warnings.some((warning) => warning.includes('История'))).toBe(true);
    expect(preview.warnings.some((warning) => warning.includes('текущего автора'))).toBe(true);
  });

  it('normalizes legacy card statuses accepted by the backend', () => {
    const bundle = cloneFixture();
    bundle.payload.cards[0].status = 'in_progress';
    bundle.payload.cards[1].status = 'done';

    const preview = parseBoardBundleText(JSON.stringify(bundle));

    expect(preview.cards.map((card) => card.status)).toEqual(['active', 'completed']);
  });

  it('rejects an unsupported format version before any server write', () => {
    const bundle = cloneFixture();
    bundle['manifest.json'].formatVersion = 2;

    expect(() => parseBoardBundleText(JSON.stringify(bundle))).toThrow(
      new BoardBundleValidationError('Версия bundle 2 не поддерживается. Ожидается версия 1.'),
    );
  });

  it('rejects broken entity references', () => {
    const bundle = cloneFixture();
    bundle.payload.cards[0].columnId = 'missing-column';

    expect(() => parseBoardBundleText(JSON.stringify(bundle))).toThrow(/отсутствующий id missing-column/);
  });

  it('chooses a repeatable non-conflicting board name', () => {
    expect(chooseImportedBoardName('Release plan', ['Release plan (импорт)', 'Release plan (импорт 2)']))
      .toBe('Release plan (импорт 3)');
  });
});
