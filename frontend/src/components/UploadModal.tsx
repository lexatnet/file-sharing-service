import { FormEvent, useState } from "react";
import { Button, Form, Modal, ProgressBar } from "react-bootstrap";

type UploadModalProps = {
  show: boolean;
  isSubmitting: boolean;
  /** Upload progress in percent, or null when no upload is running. */
  progress: number | null;
  onHide: () => void;
  onSubmit: (title: string, file: File) => Promise<void>;
};

export default function UploadModal({
  show,
  isSubmitting,
  progress,
  onHide,
  onSubmit,
}: UploadModalProps) {
  const [title, setTitle] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  function reset() {
    setTitle("");
    setSelectedFile(null);
  }

  function handleHide() {
    reset();
    onHide();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !selectedFile) {
      return;
    }
    await onSubmit(title.trim(), selectedFile);
    reset();
  }

  return (
    <Modal show={show} onHide={handleHide} centered>
      <Form onSubmit={handleSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Добавить файл</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Название</Form.Label>
            <Form.Control
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Например, Договор с подрядчиком"
            />
          </Form.Group>
          <Form.Group>
            <Form.Label>Файл</Form.Label>
            <Form.Control
              type="file"
              onChange={(event) =>
                setSelectedFile((event.target as HTMLInputElement).files?.[0] ?? null)
              }
            />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer className="flex-column align-items-stretch">
          {progress !== null && isSubmitting ? (
            <ProgressBar
              now={progress}
              label={`${progress}%`}
              striped
              animated
              className="mb-2"
            />
          ) : null}
          <div className="d-flex justify-content-between">
            <Button variant="outline-secondary" onClick={handleHide}>
              Отмена
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={isSubmitting || !title.trim() || !selectedFile}
            >
              {progress !== null && isSubmitting ? "Загрузка..." : "Сохранить"}
            </Button>
          </div>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}