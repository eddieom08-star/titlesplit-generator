'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Opportunity, AnalysisResult, getOpportunities, formatPrice, getScoreColor, triggerScrape, seedDemoData, analyzeUrl } from '@/lib/api';

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  useEffect(() => {
    loadOpportunities();
  }, []);

  async function loadOpportunities() {
    try {
      setLoading(true);
      const data = await getOpportunities();
      setOpportunities(data);
      setError(null);
    } catch (err) {
      setError('Failed to load opportunities');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerScrape() {
    try {
      setScraping(true);
      setScrapeMessage(null);
      const result = await triggerScrape();
      setScrapeMessage(result.message);
      // Refresh opportunities after a short delay to allow scraping to start
      setTimeout(() => loadOpportunities(), 5000);
    } catch (err) {
      setScrapeMessage('Failed to trigger scrape');
      console.error(err);
    } finally {
      setScraping(false);
    }
  }

  async function handleSeedData() {
    try {
      setScraping(true);
      setScrapeMessage(null);
      const result = await seedDemoData();
      setScrapeMessage(`Seeded ${result.count} demo properties`);
      await loadOpportunities();
    } catch (err) {
      setScrapeMessage('Failed to seed demo data');
      console.error(err);
    } finally {
      setScraping(false);
    }
  }

  async function handleAnalyzeUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!urlInput.trim()) return;

    try {
      setAnalyzing(true);
      setAnalysisError(null);
      setAnalysisResult(null);
      const result = await analyzeUrl(urlInput.trim());
      setAnalysisResult(result);
      // Refresh opportunities list to include the new one
      await loadOpportunities();
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'Analysis failed');
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  }

  const stats = {
    total: opportunities.length,
    highPriority: opportunities.filter(o => o.priority === 'high').length,
    totalNetBenefit: opportunities.reduce((sum, o) => sum + (o.estimated_net_benefit_per_unit || 0) * o.estimated_units, 0),
    avgScore: opportunities.length > 0
      ? Math.round(opportunities.reduce((sum, o) => sum + o.opportunity_score, 0) / opportunities.length)
      : 0,
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Title Split Finder</h1>
              <p className="text-sm text-gray-500">UK Property Investment Opportunities</p>
              {scrapeMessage && (
                <p className="text-xs text-green-600 mt-1">{scrapeMessage}</p>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleSeedData}
                disabled={scraping}
                variant="default"
              >
                {scraping ? 'Loading...' : 'Load Demo Data'}
              </Button>
              <Button
                onClick={handleTriggerScrape}
                disabled={scraping}
                variant="outline"
              >
                Run Scraper
              </Button>
              <Button onClick={loadOpportunities} variant="outline">
                Refresh
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Opportunities</CardDescription>
              <CardTitle className="text-3xl">{stats.total}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>High Priority</CardDescription>
              <CardTitle className="text-3xl text-red-600">{stats.highPriority}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Est. Net Benefit</CardDescription>
              <CardTitle className="text-3xl text-green-600">{formatPrice(stats.totalNetBenefit)}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Avg Opportunity Score</CardDescription>
              <CardTitle className="text-3xl">{stats.avgScore}/100</CardTitle>
            </CardHeader>
          </Card>
        </div>

        {/* URL Analysis */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Analyze Property URL</CardTitle>
            <CardDescription>
              Paste a property URL from Rightmove, Zoopla, OnTheMarket, or auction sites
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleAnalyzeUrl} className="flex gap-2">
              <Input
                type="url"
                placeholder="https://www.rightmove.co.uk/properties/..."
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                className="flex-1"
                disabled={analyzing}
              />
              <Button type="submit" disabled={analyzing || !urlInput.trim()}>
                {analyzing ? 'Analyzing...' : 'Analyze'}
              </Button>
            </form>

            {analysisError && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-600">{analysisError}</p>
              </div>
            )}

            {analysisResult && (
              <div className="mt-4 p-4 bg-gray-50 border rounded-lg">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="font-semibold text-lg">{analysisResult.title}</h3>
                    <p className="text-sm text-gray-500">
                      {analysisResult.city} {analysisResult.postcode}
                    </p>
                  </div>
                  <Badge
                    variant={
                      analysisResult.recommendation === 'proceed'
                        ? 'default'
                        : analysisResult.recommendation === 'review'
                        ? 'secondary'
                        : 'destructive'
                    }
                    className="text-sm"
                  >
                    {analysisResult.recommendation.toUpperCase()}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <p className="text-xs text-gray-500">Price</p>
                    <p className="font-semibold">{formatPrice(analysisResult.price)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Est. Units</p>
                    <p className="font-semibold">{analysisResult.estimated_units || 'Unknown'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Tenure</p>
                    <p className="font-semibold capitalize">{analysisResult.tenure}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Score</p>
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${getScoreColor(analysisResult.opportunity_score)}`} />
                      <span className="font-semibold">{analysisResult.opportunity_score}/100</span>
                    </div>
                  </div>
                </div>

                <div className="border-t pt-4">
                  <p className="text-xs text-gray-500 mb-2">Analysis Notes</p>
                  <ul className="text-sm space-y-1">
                    {analysisResult.analysis_notes.map((note, i) => (
                      <li key={i} className={note.startsWith('Issue') ? 'text-red-600' : note.startsWith('Warning') ? 'text-yellow-600' : 'text-green-600'}>
                        {note}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="mt-4 pt-4 border-t flex justify-between items-center">
                  <a
                    href={analysisResult.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:underline"
                  >
                    View Original Listing
                  </a>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAnalysisResult(null);
                      setUrlInput('');
                    }}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Opportunities Table */}
        <Card>
          <CardHeader>
            <CardTitle>Opportunities</CardTitle>
            <CardDescription>
              Properties identified for potential title split
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8 text-gray-500">Loading...</div>
            ) : error ? (
              <div className="text-center py-8 text-red-500">{error}</div>
            ) : opportunities.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-gray-500 mb-4">No opportunities found yet</p>
                <p className="text-sm text-gray-400">
                  Properties will appear here once the scraper finds potential title split opportunities.
                </p>
                <div className="mt-6 p-4 bg-gray-50 rounded-lg max-w-md mx-auto">
                  <p className="text-sm font-medium text-gray-700 mb-2">API Status</p>
                  <p className="text-xs text-gray-500">
                    Backend: <a href="https://titlesplit-api.onrender.com/docs" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">https://titlesplit-api.onrender.com</a>
                  </p>
                </div>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Property</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                    <TableHead className="text-center">Units</TableHead>
                    <TableHead>Tenure</TableHead>
                    <TableHead className="text-center">Score</TableHead>
                    <TableHead className="text-right">Est. Uplift</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {opportunities.map((opp) => {
                    const priorityVariant = opp.priority === 'high' ? 'destructive' : opp.priority === 'medium' ? 'default' : 'secondary';
                    const recommendationLabel = opp.recommendation === 'proceed' ? 'Proceed' : opp.recommendation === 'review' ? 'Review' : 'Decline';
                    return (
                      <TableRow key={opp.id}>
                        <TableCell className="font-medium max-w-xs truncate">
                          <a
                            href={opp.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:text-blue-600 hover:underline"
                          >
                            {opp.title}
                          </a>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm">{opp.city}</div>
                          <div className="text-xs text-gray-500">{opp.postcode}</div>
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {formatPrice(opp.price)}
                        </TableCell>
                        <TableCell className="text-center">
                          {opp.estimated_units}
                        </TableCell>
                        <TableCell className="capitalize">
                          {opp.tenure}
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex items-center justify-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${getScoreColor(opp.opportunity_score)}`} />
                            {opp.opportunity_score}
                          </div>
                        </TableCell>
                        <TableCell className="text-right text-green-600 font-medium">
                          {opp.estimated_gross_uplift_percent ? `${opp.estimated_gross_uplift_percent}%` : '-'}
                        </TableCell>
                        <TableCell>
                          <Badge variant={priorityVariant}>
                            {recommendationLabel}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <p className="text-sm text-gray-500 text-center">
            Title Split Opportunity Finder - UK Property Investment Tool
          </p>
        </div>
      </footer>
    </div>
  );
}
