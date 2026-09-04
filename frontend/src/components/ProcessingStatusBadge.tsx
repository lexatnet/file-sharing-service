import { Badge } from "react-bootstrap";

import { getProcessingVariant } from "@/lib/format";
import type { ProcessingStatus } from "@/types";

type StatusBadgeProps = {
  status: ProcessingStatus;
};

export default function ProcessingStatusBadge({ status }: StatusBadgeProps) {
  return (
    <Badge bg={getProcessingVariant(status)}>{status}</Badge>
  );
}