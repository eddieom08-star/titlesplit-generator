'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://titlesplit-api.onrender.com';

export interface SourceProgress {
  source: string;
  count: number;
}

export interface CurrentJob {
  id: string;
  started_at: string;
  progress_percent: number;
  sources: SourceProgress[];
  total_found: number;
}

export interface LastCompleted {
  id: string;
  completed_at: string;
  properties_found: number;
  new_properties: number;
}

// Raw API response types
interface ApiJobSummary {
  id: string;
  status: string;
  progress_percent: number;
  started_at: string;
  completed_at: string | null;
  total_scraped: number;
  total_new: number;
  source_results: Record<string, { scraped?: number; new?: number; error?: string }> | null;
}

interface ApiStatusResponse {
  current_status: 'idle' | 'running';
  current_job: ApiJobSummary | null;
  last_completed: ApiJobSummary | null;
}

export interface StatusTransition {
  wasRunning: boolean;
  isNowIdle: boolean;
  lastCompleted: ApiJobSummary | null;
}

export interface UseScraperStatusReturn {
  status: 'idle' | 'running' | 'error';
  currentJob: CurrentJob | null;
  lastCompleted: LastCompleted | null;
  isRunning: boolean;
  errorMessage: string | null;
  refetch: () => Promise<StatusTransition | null>;
}

function transformJob(job: ApiJobSummary | null): CurrentJob | null {
  if (!job) return null;

  // Transform source_results dict to sources array
  const sources: SourceProgress[] = [];
  if (job.source_results) {
    for (const [source, data] of Object.entries(job.source_results)) {
      if (typeof data === 'object' && data !== null && !data.error) {
        sources.push({
          source: source.charAt(0).toUpperCase() + source.slice(1),
          count: data.scraped || 0,
        });
      }
    }
  }

  return {
    id: job.id,
    started_at: job.started_at,
    progress_percent: job.progress_percent,
    sources,
    total_found: job.total_scraped,
  };
}

function transformLastCompleted(job: ApiJobSummary | null): LastCompleted | null {
  if (!job || !job.completed_at) return null;

  return {
    id: job.id,
    completed_at: job.completed_at,
    properties_found: job.total_scraped,
    new_properties: job.total_new,
  };
}

export function useScraperStatus(): UseScraperStatusReturn {
  const [status, setStatus] = useState<'idle' | 'running' | 'error'>('idle');
  const [currentJob, setCurrentJob] = useState<CurrentJob | null>(null);
  const [lastCompleted, setLastCompleted] = useState<LastCompleted | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const prevStatusRef = useRef<string>('idle');

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/scraper/status`, {
        cache: 'no-store',
      });
      if (!res.ok) {
        throw new Error('Failed to fetch scraper status');
      }
      const data: ApiStatusResponse = await res.json();

      // Detect status transitions
      const prevStatus = prevStatusRef.current;
      const newStatus = data.current_status;
      prevStatusRef.current = newStatus;

      setStatus(newStatus);
      setCurrentJob(transformJob(data.current_job));
      setLastCompleted(transformLastCompleted(data.last_completed));
      setErrorMessage(null);

      // Return transition info for toast notifications
      return {
        wasRunning: prevStatus === 'running',
        isNowIdle: newStatus === 'idle',
        lastCompleted: data.last_completed,
      };
    } catch (err) {
      console.error('Error fetching scraper status:', err);
      setStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'Unknown error');
      return null;
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    const pollInterval = status === 'running' ? 2000 : 30000;
    intervalRef.current = setInterval(fetchStatus, pollInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [status, fetchStatus]);

  return {
    status,
    currentJob,
    lastCompleted,
    isRunning: status === 'running',
    errorMessage,
    refetch: fetchStatus,
  };
}
