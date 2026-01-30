'use client';

import { useScraperStatus } from '@/hooks/useScraperStatus';
import { cn } from '@/lib/utils';

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return 'just now';
  } else if (diffMinutes < 60) {
    return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  } else {
    return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  }
}

export function ScraperStatus() {
  const { status, currentJob, lastCompleted, isRunning } = useScraperStatus();

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-50 border rounded-lg text-sm">
      {/* Status Indicator Dot */}
      <div className="flex items-center gap-2">
        <div
          className={cn(
            'w-2.5 h-2.5 rounded-full',
            isRunning
              ? 'bg-green-500 animate-pulse'
              : status === 'error'
              ? 'bg-red-500'
              : 'bg-gray-400'
          )}
        />
        <span className="font-medium text-gray-700">
          {isRunning ? 'Scraping' : status === 'error' ? 'Error' : 'Idle'}
        </span>
      </div>

      {/* Divider */}
      <div className="w-px h-4 bg-gray-300" />

      {/* Status Details */}
      {isRunning && currentJob ? (
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* Progress Text */}
          <span className="text-gray-600 whitespace-nowrap">
            {currentJob.progress_percent}%
          </span>

          {/* Progress Bar */}
          <div className="flex-1 min-w-[100px] max-w-[200px]">
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-300 ease-out"
                style={{ width: `${currentJob.progress_percent}%` }}
              />
            </div>
          </div>

          {/* Source Breakdown */}
          <div className="flex items-center gap-1.5 text-gray-500 text-xs">
            {currentJob.sources.map((source, index) => (
              <span key={source.source}>
                {index > 0 && <span className="text-gray-300 mr-1.5">|</span>}
                <span className="font-medium">{source.source}:</span>{' '}
                <span>{source.count}</span>
              </span>
            ))}
            {currentJob.sources.length === 0 && (
              <span>Starting...</span>
            )}
          </div>
        </div>
      ) : lastCompleted ? (
        <span className="text-gray-500">
          Last run: {formatTimeAgo(lastCompleted.completed_at)} -{' '}
          <span className="font-medium text-gray-700">
            {lastCompleted.properties_found} properties found
          </span>
        </span>
      ) : (
        <span className="text-gray-500">No recent scraping activity</span>
      )}
    </div>
  );
}
