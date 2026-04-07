import type { PropsWithChildren } from 'react';
import { QueryProvider } from '@/app/providers/QueryProvider';
import { DevSessionProvider } from '@/app/providers/DevSessionProvider';
import { AppearanceProvider } from '@/app/providers/AppearanceProvider';
import { ProjectRoadmapSeedProvider } from '@/features/bootstrap/providers/ProjectRoadmapSeedProvider';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryProvider>
      <DevSessionProvider>
        <ProjectRoadmapSeedProvider>
          <AppearanceProvider>{children}</AppearanceProvider>
        </ProjectRoadmapSeedProvider>
      </DevSessionProvider>
    </QueryProvider>
  );
}
