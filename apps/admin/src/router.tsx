import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router';
import React, { lazy } from 'react';

import AppShell from '@/layout/AppShell';

const LoginPage = lazy(() => import('@/pages/LoginPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const ApplicationsPage = lazy(() => import('@/pages/ApplicationsPage'));
const AIPage = lazy(() => import('@/pages/AIPage'));
const KnowledgePage = lazy(() => import('@/pages/KnowledgePage'));
const TeamPage = lazy(() => import('@/pages/TeamPage'));
const AgentPage = lazy(() => import('@/pages/AgentPage'));
const OperationsPage = lazy(() => import('@/pages/OperationsPage'));
const PlatformPage = lazy(() => import('@/pages/PlatformPage'));

const rootRoute = createRootRoute({ component: Outlet });
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: LoginPage,
});
const authenticatedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: '_authenticated',
  component: AppShell,
});
const dashboardRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/',
  component: DashboardPage,
});
const applicationsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/applications',
  component: ApplicationsPage,
});
const aiRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/ai',
  component: AIPage,
});
const knowledgeRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/knowledge',
  component: KnowledgePage,
});
const teamRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/team',
  component: TeamPage,
});
const handoffsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/handoffs',
  component: AgentPage,
});
const operationsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/operations',
  component: OperationsPage,
});
const platformRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/platform',
  component: PlatformPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  authenticatedRoute.addChildren([
    dashboardRoute,
    applicationsRoute,
    aiRoute,
    knowledgeRoute,
    teamRoute,
    handoffsRoute,
    operationsRoute,
    platformRoute,
  ]),
]);

const configuredBasePath = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  basepath: configuredBasePath,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
