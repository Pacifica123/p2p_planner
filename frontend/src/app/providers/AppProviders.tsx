import type { PropsWithChildren } from 'react';
import { QueryProvider } from '@/app/providers/QueryProvider';
import { AuthSessionProvider } from '@/app/providers/AuthSessionProvider';
import { AppearanceProvider } from '@/app/providers/AppearanceProvider';
import { ProjectRoadmapSeedProvider } from '@/features/bootstrap/providers/ProjectRoadmapSeedProvider';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryProvider>
      <AuthSessionProvider>
        <ProjectRoadmapSeedProvider>
          <AppearanceProvider>{children}</AppearanceProvider>
        </ProjectRoadmapSeedProvider>
      </AuthSessionProvider>
    </QueryProvider>
  );
}
