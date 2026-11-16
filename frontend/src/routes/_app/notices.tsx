import { createFileRoute } from "@tanstack/react-router";
import { NoticesScreen } from "@/components/notices-screen";

export const Route = createFileRoute("/_app/notices")({ component: NoticesScreen });
