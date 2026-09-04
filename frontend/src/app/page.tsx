"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Card,
  Col,
  Container,
  Row,
  Spinner,
} from "react-bootstrap";

import AlertsTable from "@/components/AlertsTable";
import FilesTable from "@/components/FilesTable";
import Header from "@/components/Header";
import UploadModal from "@/components/UploadModal";
import { getAlerts, getFiles, uploadFile } from "@/lib/api";
import type { AlertItem, FileItem } from "@/types";

export default function Page() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const [filesData, alertsData] = await Promise.all([getFiles(), getAlerts()]);
      setFiles(filesData);
      setAlerts(alertsData);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Произошла ошибка");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleUpload(title: string, file: File) {
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await uploadFile(title, file);
      setShowModal(false);
      await loadData();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Произошла ошибка");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Container fluid className="py-4 px-4 bg-light min-vh-100">
      <Row className="justify-content-center">
        <Col xxl={10} xl={11}>
          <Card className="shadow-sm border-0 mb-4">
            <Card.Body className="p-4">
              <Header
                onRefresh={() => void loadData()}
                onAddFile={() => setShowModal(true)}
              />
            </Card.Body>
          </Card>

          {errorMessage ? (
            <Alert variant="danger" className="shadow-sm">
              {errorMessage}
            </Alert>
          ) : null}

          <Card className="shadow-sm border-0 mb-4">
            <Card.Header className="bg-white border-0 pt-4 px-4">
              <div className="d-flex justify-content-between align-items-center">
                <h2 className="h5 mb-0">Файлы</h2>
                <Badge bg="secondary">{files.length}</Badge>
              </div>
            </Card.Header>
            <Card.Body className="px-4 pb-4">
              {isLoading ? (
                <div className="d-flex justify-content-center py-5">
                  <Spinner animation="border" />
                </div>
              ) : (
                <FilesTable files={files} isLoading={isLoading} />
              )}
            </Card.Body>
          </Card>

          <Card className="shadow-sm border-0">
            <Card.Header className="bg-white border-0 pt-4 px-4">
              <div className="d-flex justify-content-between align-items-center">
                <h2 className="h5 mb-0">Алерты</h2>
                <Badge bg="secondary">{alerts.length}</Badge>
              </div>
            </Card.Header>
            <Card.Body className="px-4 pb-4">
              {isLoading ? (
                <div className="d-flex justify-content-center py-5">
                  <Spinner animation="border" />
                </div>
              ) : (
                <AlertsTable alerts={alerts} isLoading={isLoading} />
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <UploadModal
        show={showModal}
        isSubmitting={isSubmitting}
        onHide={() => setShowModal(false)}
        onSubmit={handleUpload}
      />
    </Container>
  );
}