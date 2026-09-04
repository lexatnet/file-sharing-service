import { Badge } from "react-bootstrap";

import type { FileItem } from "@/types";

type FileScanBadgeProps = {
  file: FileItem;
};

export default function FileScanBadge({ file }: FileScanBadgeProps) {
  return (
    <div className="d-flex flex-column gap-1">
      <Badge bg={file.requires_attention ? "warning" : "success"}>
        {file.scan_status ?? "pending"}
      </Badge>
      <span className="small text-secondary">
        {file.scan_details ?? "Ожидает обработки"}
      </span>
    </div>
  );
}