import { Badge, Button, Table } from "react-bootstrap";

import FileScanBadge from "@/components/FileScanBadge";
import ProcessingStatusBadge from "@/components/ProcessingStatusBadge";
import DownloadButton from "@/components/DownloadButton";
import { formatDate, formatSize } from "@/lib/format";
import type { FileItem } from "@/types";

type FilesTableProps = {
  files: FileItem[];
  isLoading: boolean;
};

export default function FilesTable({ files, isLoading }: FilesTableProps) {
  if (isLoading) {
    return null;
  }

  return (
    <div className="table-responsive">
      <Table hover bordered className="align-middle mb-0">
        <thead className="table-light">
          <tr>
            <th>Название</th>
            <th>Файл</th>
            <th>MIME</th>
            <th>Размер</th>
            <th>Статус</th>
            <th>Проверка</th>
            <th>Создан</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {files.length === 0 ? (
            <tr>
              <td colSpan={8} className="text-center py-4 text-secondary">
                Файлы пока не загружены
              </td>
            </tr>
          ) : (
            files.map((file) => (
              <tr key={file.id}>
                <td>
                  <div className="fw-semibold">{file.title}</div>
                  <div className="small text-secondary">{file.id}</div>
                </td>
                <td>{file.original_name}</td>
                <td>{file.mime_type}</td>
                <td>{formatSize(file.size)}</td>
                <td>
                  <ProcessingStatusBadge status={file.processing_status} />
                </td>
                <td>
                  <FileScanBadge file={file} />
                </td>
                <td>{formatDate(file.created_at)}</td>
                <td className="text-nowrap">
                  <DownloadButton file={file} />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </Table>
    </div>
  );
}