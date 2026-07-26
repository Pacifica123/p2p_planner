import { ChangeEvent, useRef, useState } from 'react';
import {
  BoardBundlePreview,
  chooseImportedBoardName,
  readBoardBundleFile,
} from '@/features/integrations/lib/boardBundle';
import {
  BoardImportProgress,
  importBoardCopy,
} from '@/features/integrations/lib/importBoardCopy';
import { Button } from '@/shared/ui/Button';
import { ErrorState } from '@/shared/ui/ErrorState';
import { TextField } from '@/shared/ui/Field';
import { Panel } from '@/shared/ui/Panel';

interface BoardImportPanelProps {
  workspaceId: string;
  existingBoardNames: string[];
  onImported: (boardId: string) => void | Promise<void>;
}

function dateLabel(value?: string) {
  if (!value) return 'не указано';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function BoardImportPanel({
  workspaceId,
  existingBoardNames,
  onImported,
}: BoardImportPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<BoardBundlePreview | null>(null);
  const [targetName, setTargetName] = useState('');
  const [readError, setReadError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [progress, setProgress] = useState<BoardImportProgress | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setReadError(null);
    setImportError(null);
    setProgress(null);
    setPreview(null);

    try {
      const nextPreview = await readBoardBundleFile(file);
      setPreview(nextPreview);
      setTargetName(chooseImportedBoardName(nextPreview.board.name, existingBoardNames));
    } catch (error) {
      setReadError(error instanceof Error ? error.message : 'Не удалось прочитать bundle.');
    }
  }

  async function handleImport() {
    if (!preview || isImporting) return;
    setImportError(null);
    setIsImporting(true);
    setProgress(null);

    try {
      const result = await importBoardCopy({
        workspaceId,
        boardName: targetName,
        preview,
        onProgress: setProgress,
      });
      await onImported(result.boardId);
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Не удалось импортировать доску.');
    } finally {
      setIsImporting(false);
    }
  }

  function resetPreview() {
    if (isImporting) return;
    setPreview(null);
    setReadError(null);
    setImportError(null);
    setProgress(null);
    setTargetName('');
  }

  return (
    <Panel
      title="Импорт доски из JSON"
      description="Bundle проверяется в браузере и создаётся как новая копия. Существующие доски не перезаписываются."
      actions={(
        <>
          <input
            ref={inputRef}
            hidden
            type="file"
            accept=".json,application/json"
            onChange={(event) => void handleFileChange(event)}
            data-testid="board-import-file-input"
          />
          <Button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={isImporting}
          >
            Выбрать JSON
          </Button>
        </>
      )}
    >
      {readError ? (
        <ErrorState
          compact
          title="Файл не прошёл проверку"
          description={readError}
          onRetry={() => inputRef.current?.click()}
        />
      ) : null}

      {!preview && !readError ? (
        <p className="muted">
          Поддерживается board-level файл формата p2p_planner_bundle версии 1 размером до 10 МБ.
        </p>
      ) : null}

      {preview ? (
        <div className="board-import-preview" data-testid="board-import-preview">
          <div className="board-import-preview__summary">
            <div>
              <span className="muted">Файл</span>
              <strong>{preview.fileName}</strong>
            </div>
            <div>
              <span className="muted">Исходная доска</span>
              <strong>{preview.board.name}</strong>
            </div>
            <div>
              <span className="muted">Создан bundle</span>
              <strong>{dateLabel(preview.generatedAt)}</strong>
            </div>
            <div>
              <span className="muted">Состав</span>
              <strong>
                {preview.counts.columns} колонок, {preview.counts.cards} карточек
              </strong>
            </div>
            <div>
              <span className="muted">Дополнительно</span>
              <strong>
                {preview.counts.labels} меток, {preview.counts.checklists} списков, {preview.counts.comments} комментариев
              </strong>
            </div>
          </div>

          <TextField
            label="Название новой доски"
            value={targetName}
            maxLength={200}
            onChange={(event) => setTargetName(event.target.value)}
            disabled={isImporting}
          />

          {preview.warnings.length ? (
            <div className="board-import-preview__warnings">
              <strong>Что изменится при импорте</strong>
              <ul>
                {preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </div>
          ) : null}

          {progress ? (
            <div className="board-import-progress" aria-live="polite">
              <div className="entity-header">
                <strong>{progress.message}</strong>
                <span className="muted">{progress.completed}/{progress.total}</span>
              </div>
              <progress max={progress.total} value={progress.completed} />
            </div>
          ) : null}

          {importError ? (
            <ErrorState compact title="Импорт не завершён" description={importError} />
          ) : null}

          <div className="inline-actions">
            <Button
              type="button"
              variant="primary"
              onClick={() => void handleImport()}
              disabled={isImporting || !targetName.trim()}
              data-testid="board-import-confirm"
            >
              {isImporting ? 'Создаём копию…' : 'Создать копию'}
            </Button>
            <Button type="button" variant="ghost" onClick={resetPreview} disabled={isImporting}>
              Отменить
            </Button>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
