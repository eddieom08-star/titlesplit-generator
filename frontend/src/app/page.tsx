'use client';

import { useEffect, useState, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/toaster';
import { ScraperStatus } from '@/components/ScraperStatus';
import { useScraperStatus } from '@/hooks/useScraperStatus';
import { Opportunity, AnalysisResult, ValuationResult, OpportunityFilters, getOpportunities, formatPrice, getScoreColor, triggerScrape, analyzeUrl, getValuation, archiveProperty } from '@/lib/api';

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();
  const { isRunning, lastCompleted, refetch: refetchStatus } = useScraperStatus();
  const prevIsRunningRef = useRef(false);
  const [urlInput, setUrlInput] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [manualUnits, setManualUnits] = useState<string>('');
  const [manualPostcode, setManualPostcode] = useState<string>('');
  const [valuationResult, setValuationResult] = useState<ValuationResult | null>(null);
  const [valuating, setValuating] = useState(false);
  // Filters
  const [filters, setFilters] = useState<OpportunityFilters>({
    minScore: 0,
    sortBy: 'score',
    includeArchived: false,
  });
  const [archiving, setArchiving] = useState<string | null>(null);

  useEffect(() => {
    loadOpportunities();
  }, [filters]);

  // Watch for scraping completion and show toast
  useEffect(() => {
    if (prevIsRunningRef.current && !isRunning && lastCompleted) {
      // Scraping just finished
      toast({
        title: 'Scraping Complete',
        description: `Found ${lastCompleted.properties_found} properties (${lastCompleted.new_properties} new)`,
        variant: 'success',
      });
      // Refresh opportunities
      loadOpportunities();
    }
    prevIsRunningRef.current = isRunning;
  }, [isRunning, lastCompleted, toast]);

  async function loadOpportunities() {
    try {
      setLoading(true);
      const data = await getOpportunities(filters);
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
      await triggerScrape();
      toast({
        title: 'Scraper Started',
        description: 'Searching for new opportunities...',
        variant: 'info',
      });
      // Refresh status immediately
      refetchStatus();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to start scraper';
      // Check if it's already running (409 conflict)
      if (errorMessage.includes('already running')) {
        toast({
          title: 'Scraper Already Running',
          description: 'A scrape is already in progress',
          variant: 'warning',
        });
      } else {
        toast({
          title: 'Error',
          description: errorMessage,
          variant: 'error',
        });
      }
      console.error(err);
    }
  }

  async function handleArchive(propertyId: string) {
    try {
      setArchiving(propertyId);
      await archiveProperty(propertyId);
      await loadOpportunities();
    } catch (err) {
      console.error('Failed to archive property', err);
    } finally {
      setArchiving(null);
    }
  }

  async function handleAnalyzeUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!urlInput.trim()) return;

    try {
      setAnalyzing(true);
      setAnalysisError(null);
      setAnalysisResult(null);
      setValuationResult(null);
      const result = await analyzeUrl(urlInput.trim());
      setAnalysisResult(result);
      // Pre-fill manual fields
      setManualUnits(result.estimated_units?.toString() || '');
      setManualPostcode(result.postcode || '');
      // Refresh opportunities list to include the new one
      await loadOpportunities();
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'Analysis failed');
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleGetValuation() {
    if (!analysisResult || !manualUnits || !manualPostcode) return;

    const units = parseInt(manualUnits, 10);
    if (isNaN(units) || units < 1) {
      setAnalysisError('Please enter a valid number of units');
      return;
    }

    try {
      setValuating(true);
      setAnalysisError(null);
      const result = await getValuation(
        manualPostcode,
        analysisResult.price,
        units
      );
      setValuationResult(result);
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'Valuation failed');
      console.error(err);
    } finally {
      setValuating(false);
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
            </div>
            <div className="flex items-center gap-3">
              <ScraperStatus />
              <Button
                onClick={handleTriggerScrape}
                disabled={isRunning}
                variant="outline"
                size="sm"
              >
                {isRunning ? 'Scraping...' : 'Run Scraper'}
              </Button>
              <Button onClick={loadOpportunities} variant="outline" size="sm">
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

                {/* Manual Input for PropertyData Valuation */}
                <div className="mt-4 pt-4 border-t">
                  <p className="text-sm font-medium mb-3">Get PropertyData Valuation</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                    <div>
                      <label className="text-xs text-gray-500">Units</label>
                      <Input
                        type="number"
                        min="1"
                        max="20"
                        placeholder="e.g., 3"
                        value={manualUnits}
                        onChange={(e) => setManualUnits(e.target.value)}
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">Postcode</label>
                      <Input
                        type="text"
                        placeholder="e.g., PR8 3DN"
                        value={manualPostcode}
                        onChange={(e) => setManualPostcode(e.target.value)}
                        className="mt-1"
                      />
                    </div>
                    <div className="flex items-end">
                      <Button
                        onClick={handleGetValuation}
                        disabled={valuating || !manualUnits || !manualPostcode}
                        className="w-full"
                      >
                        {valuating ? 'Getting...' : 'Get Valuation'}
                      </Button>
                    </div>
                  </div>

                  {valuationResult && valuationResult.status === 'success' && (
                    <div className="space-y-4">
                      {/* Main Valuation */}
                      <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                        <div className="flex items-center justify-between mb-3">
                          <span className="font-semibold text-green-800">PropertyData Valuation</span>
                          <Badge variant={valuationResult.recommendation === 'proceed' ? 'default' : valuationResult.recommendation === 'review' ? 'secondary' : 'destructive'}>
                            {valuationResult.recommendation?.toUpperCase()}
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          <div>
                            <p className="text-xs text-gray-500">Est. Unit Value</p>
                            <p className="font-semibold">{valuationResult.estimated_unit_value ? formatPrice(valuationResult.estimated_unit_value) : 'N/A'}</p>
                            <p className="text-xs text-gray-400">
                              {valuationResult.unit_value_low && valuationResult.unit_value_high
                                ? `${formatPrice(valuationResult.unit_value_low)} - ${formatPrice(valuationResult.unit_value_high)}`
                                : valuationResult.unit_value_confidence + ' confidence'}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">Total Separated</p>
                            <p className="font-semibold">{valuationResult.total_separated_value ? formatPrice(valuationResult.total_separated_value) : 'N/A'}</p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">Gross Uplift</p>
                            <p className="font-semibold text-green-600">{valuationResult.gross_uplift ? formatPrice(valuationResult.gross_uplift) : 'N/A'}</p>
                            <p className="text-xs text-gray-400">{valuationResult.gross_uplift_percent}%</p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">Net Per Unit</p>
                            <p className="font-semibold text-green-600">{valuationResult.net_per_unit ? formatPrice(valuationResult.net_per_unit) : 'N/A'}</p>
                            <p className="text-xs text-gray-400">{valuationResult.meets_threshold ? '✓ Above £2k threshold' : '✗ Below threshold'}</p>
                          </div>
                        </div>
                        {valuationResult.avg_price_per_sqf && (
                          <div className="mt-3 pt-3 border-t border-green-200">
                            <p className="text-xs text-gray-500">Avg Price/sqft (from EPC data)</p>
                            <p className="font-semibold">£{valuationResult.avg_price_per_sqf}/sqft</p>
                          </div>
                        )}
                      </div>

                      {/* Land Registry Comparables */}
                      {valuationResult.comparable_sales && valuationResult.comparable_sales.length > 0 && (
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                          <p className="font-semibold text-blue-800 mb-3">Land Registry Comparables</p>
                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-left text-gray-500">
                                  <th className="pb-2">Address</th>
                                  <th className="pb-2">Date</th>
                                  <th className="pb-2 text-right">Price</th>
                                  <th className="pb-2 text-right">Sqft</th>
                                  <th className="pb-2 text-right">£/sqft</th>
                                </tr>
                              </thead>
                              <tbody>
                                {valuationResult.comparable_sales.map((sale, i) => (
                                  <tr key={i} className="border-t border-blue-100">
                                    <td className="py-2 pr-2 max-w-[200px] truncate">{sale.address}</td>
                                    <td className="py-2 pr-2">{sale.date}</td>
                                    <td className="py-2 text-right font-medium">{sale.price ? formatPrice(sale.price) : '-'}</td>
                                    <td className="py-2 text-right">{sale.sqf || '-'}</td>
                                    <td className="py-2 text-right">{sale.price_per_sqf ? `£${sale.price_per_sqf}` : '-'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {valuationResult && valuationResult.status !== 'success' && (
                    <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                      {valuationResult.message || 'Could not get valuation data'}
                    </div>
                  )}
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
                      setValuationResult(null);
                      setUrlInput('');
                      setManualUnits('');
                      setManualPostcode('');
                    }}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Filters */}
        <Card className="mb-8">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">Filters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Min Score</label>
                <Select
                  value={String(filters.minScore ?? 0)}
                  onValueChange={(value) => setFilters({ ...filters, minScore: parseInt(value) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">All (0+)</SelectItem>
                    <SelectItem value="50">50+</SelectItem>
                    <SelectItem value="60">60+</SelectItem>
                    <SelectItem value="70">70+</SelectItem>
                    <SelectItem value="80">80+</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Tenure</label>
                <Select
                  value={filters.tenure || 'all'}
                  onValueChange={(value) => setFilters({ ...filters, tenure: value === 'all' ? undefined : value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="freehold">Freehold</SelectItem>
                    <SelectItem value="leasehold">Leasehold</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Min Units</label>
                <Select
                  value={String(filters.minUnits ?? 2)}
                  onValueChange={(value) => setFilters({ ...filters, minUnits: parseInt(value) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1+</SelectItem>
                    <SelectItem value="2">2+</SelectItem>
                    <SelectItem value="3">3+</SelectItem>
                    <SelectItem value="4">4+</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Sort By</label>
                <Select
                  value={filters.sortBy || 'score'}
                  onValueChange={(value) => setFilters({ ...filters, sortBy: value as 'score' | 'price' | 'date' | 'uplift' })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="score">Score</SelectItem>
                    <SelectItem value="price">Price</SelectItem>
                    <SelectItem value="date">Date</SelectItem>
                    <SelectItem value="uplift">Uplift</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={filters.includeArchived}
                    onChange={(e) => setFilters({ ...filters, includeArchived: e.target.checked })}
                    className="rounded"
                  />
                  Show Archived
                </label>
              </div>
              <div className="flex items-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setFilters({ minScore: 0, sortBy: 'score', includeArchived: false })}
                >
                  Reset Filters
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Opportunities Table */}
        <Card>
          <CardHeader>
            <CardTitle>Opportunities</CardTitle>
            <CardDescription>
              Properties identified for potential title split ({opportunities.length} found)
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
                    <TableHead></TableHead>
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
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <a
                              href={`/property/${opp.id}`}
                              className="text-sm text-blue-600 hover:underline"
                            >
                              Details
                            </a>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleArchive(opp.id)}
                              disabled={archiving === opp.id}
                              className="text-xs text-gray-400 hover:text-red-600"
                            >
                              {archiving === opp.id ? '...' : 'Archive'}
                            </Button>
                          </div>
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
