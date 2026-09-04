import { Button } from "react-bootstrap";

type HeaderProps = {
  onRefresh: () => void;
  onAddFile: () => void;
};

export default function Header({ onRefresh, onAddFile }: HeaderProps) {
  return (
    <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
      <div>
        <h1 className="h3 mb-2">Управление файлами</h1>
        <p className="text-secondary mb-0">
          Загрузка файлов, просмотр статусов обработки и ленты алертов.
        </p>
      </div>
      <div className="d-flex gap-2">
        <Button variant="outline-secondary" onClick={onRefresh}>
          Обновить
        </Button>
        <Button variant="primary" onClick={onAddFile}>
          Добавить файл
        </Button>
      </div>
    </div>
  );
}
