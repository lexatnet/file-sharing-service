import type { Metadata } from "next";
import 'bootstrap/dist/css/bootstrap.min.css';
import { Container } from "react-bootstrap";

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: 'Тестовое задание Fullstack',
    description: 'Тестовое задание Fullstack',
    icons: {
      icon: '/favicon.ico',
    },
  };
}

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang='ru'>
      <body>
        <Container fluid className='p-0'>
            {children}
        </Container>
      </body>
    </html>
  );
}
