import { Button } from "react-bootstrap";

import { getDownloadUrl } from "@/lib/api";
import type { FileItem } from "@/types";

type FileRowProps = {
  file: FileItem;
};

export default function DownloadButton({ file }: FileRowProps) {
  return (
    <Button
      as="a"
      href={getDownloadUrl(file.id)}
      variant="outline-primary"
      size="sm"
    >
      Скачать
    </Button>
  );
}