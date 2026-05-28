import { FormEvent, useState } from 'react';
import { useCreateCardMutation } from '@/features/cards/hooks/useCards';
import { useOptionalLocalFirstBoard } from '@/features/localFirst/context/LocalFirstBoardContext';
import { Button } from '@/shared/ui/Button';

interface CreateCardInlineFormProps {
  boardId: string;
  columnId: string;
}

export function CreateCardInlineForm({ boardId, columnId }: CreateCardInlineFormProps) {
  const createCardMutation = useCreateCardMutation(boardId);
  const localFirst = useOptionalLocalFirstBoard();
  const [title, setTitle] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) return;

    if (localFirst?.boardId === boardId) {
      localFirst.enqueueCreateCard({ title: title.trim(), columnId });
      setTitle('');
      return;
    }

    createCardMutation.mutate(
      { title: title.trim(), columnId },
      {
        onSuccess: () => setTitle(''),
      },
    );
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <div className="inline-form__row inline-form__row--tight">
        <input
          data-testid="card-create-input"
          className="field__input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Новая карточка"
        />
        <Button data-testid="card-create-submit" type="submit" iconOnly disabled={createCardMutation.isPending} title="Добавить карточку" aria-label="Добавить карточку">
          {createCardMutation.isPending || localFirst?.isFlushing ? '…' : '＋'}
        </Button>
      </div>
    </form>
  );
}
