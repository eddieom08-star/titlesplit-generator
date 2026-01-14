'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  PropertyDetail,
  RecalculatedAnalysis,
  GDVReport,
  FloorplanAnalysis,
  getPropertyDetail,
  updateManualInput,
  generateGDVReport,
  uploadFloorplan,
  formatPrice,
  getScoreColor,
} from '@/lib/api';

export default function PropertyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const propertyId = params.id as string;

  const [property, setProperty] = useState<PropertyDetail | null>(null);
  const [analysis, setAnalysis] = useState<RecalculatedAnalysis | null>(null);
  const [gdvReport, setGdvReport] = useState<GDVReport | null>(null);
  const [floorplanAnalysis, setFloorplanAnalysis] = useState<FloorplanAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [uploadingFloorplan, setUploadingFloorplan] = useState(false);
  const [floorplanFile, setFloorplanFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [postcode, setPostcode] = useState<string>('');
  const [city, setCity] = useState<string>('');
  const [verifiedTenure, setVerifiedTenure] = useState<string>('');
  const [titleNumber, setTitleNumber] = useState<string>('');
  const [isSingleTitle, setIsSingleTitle] = useState<string>('');
  const [verifiedUnits, setVerifiedUnits] = useState<string>('');
  const [planningChecked, setPlanningChecked] = useState(false);
  const [conservationArea, setConservationArea] = useState(false);
  const [listedBuilding, setListedBuilding] = useState(false);
  const [article4, setArticle4] = useState(false);
  const [siteVisited, setSiteVisited] = useState(false);
  const [conditionRating, setConditionRating] = useState<string>('');
  const [structuralConcerns, setStructuralConcerns] = useState<string>('');
  const [revisedPrice, setRevisedPrice] = useState<string>('');

  useEffect(() => {
    loadProperty();
  }, [propertyId]);

  async function loadProperty() {
    try {
      setLoading(true);
      setError(null);
      const data = await getPropertyDetail(propertyId);
      setProperty(data);

      // Pre-fill property core data
      if (data.postcode) setPostcode(data.postcode);
      if (data.city) setCity(data.city);

      // Pre-fill form with existing manual inputs
      if (data.manual_inputs) {
        const mi = data.manual_inputs;
        if (mi.verified_tenure) setVerifiedTenure(mi.verified_tenure);
        if (mi.title_number) setTitleNumber(mi.title_number);
        if (mi.is_single_title !== null) setIsSingleTitle(mi.is_single_title ? 'yes' : 'no');
        if (mi.verified_units) setVerifiedUnits(mi.verified_units.toString());
        setPlanningChecked(mi.planning_checked);
        if (mi.planning_constraints) {
          setConservationArea(!!mi.planning_constraints.conservation_area);
          setListedBuilding(!!mi.planning_constraints.listed_building);
          setArticle4(!!mi.planning_constraints.article_4);
        }
        setSiteVisited(mi.site_visited);
        if (mi.condition_rating) setConditionRating(mi.condition_rating);
        if (mi.structural_concerns) setStructuralConcerns(mi.structural_concerns);
        if (mi.revised_asking_price) setRevisedPrice(mi.revised_asking_price.toString());
        if (mi.floorplan_analysis) setFloorplanAnalysis(mi.floorplan_analysis);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load property';
      setError(`Error loading property: ${message}. The backend may be experiencing issues.`);
      console.error('Property load error:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateGDVReport() {
    if (!property) return;

    try {
      setGeneratingReport(true);
      setError(null);

      const report = await generateGDVReport(propertyId, {
        title_number: titleNumber || undefined,
      });
      setGdvReport(report);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate GDV report');
      console.error(err);
    } finally {
      setGeneratingReport(false);
    }
  }

  function downloadGDVReportMarkdown() {
    if (!gdvReport || !property) return;

    const ltvAmount = Math.round(gdvReport.total_gdv * 0.75);

    const markdown = `# GDV Report - ${property.title}

**Report Date:** ${new Date(gdvReport.report_date).toLocaleString()}
**Data Freshness:** ${gdvReport.data_freshness}
**Confidence Level:** ${gdvReport.gdv_confidence.toUpperCase()}

---

## GDV Summary

| Metric | Value |
|--------|-------|
| **Total GDV** | ${formatPrice(gdvReport.total_gdv)} |
| **GDV Range** | ${formatPrice(gdvReport.gdv_range_low)} - ${formatPrice(gdvReport.gdv_range_high)} |
| **75% LTV** | ${formatPrice(ltvAmount)} |
| **Asking Price** | ${formatPrice(gdvReport.asking_price)} |
| **Gross Uplift** | ${formatPrice(gdvReport.gross_uplift)} (${gdvReport.gross_uplift_percent}%) |
| **Net Uplift** | ${formatPrice(gdvReport.net_uplift)} (${gdvReport.net_uplift_percent}%) |

---

## Unit-by-Unit Valuations

| Unit | Beds | Estimated Value | Range | Confidence | Method |
|------|------|-----------------|-------|------------|--------|
${gdvReport.unit_valuations.map(u =>
  `| ${u.unit_identifier} | ${u.beds || '-'} | ${formatPrice(u.estimated_value)} | ${formatPrice(u.value_range_low)} - ${formatPrice(u.value_range_high)} | ${u.confidence} | ${u.primary_method} |`
).join('\n')}

---

## Costs & Net Profit

### Title Split Costs
- Base costs: ${formatPrice(gdvReport.title_split_costs)}
${gdvReport.refurbishment_budget ? `- Refurbishment: ${formatPrice(gdvReport.refurbishment_budget)}` : ''}
- **Total Costs:** ${formatPrice(gdvReport.total_costs)}

### Net Profit Analysis
- **Net Profit Per Unit:** ${formatPrice(gdvReport.net_profit_per_unit)}
- **Total Net Uplift:** ${formatPrice(gdvReport.net_uplift)} (${gdvReport.net_uplift_percent}% return)

---

## Comparable Evidence

- **Total Comparables:** ${gdvReport.comparables_summary.count}
${gdvReport.comparables_summary.price_range ? `- **Price Range:** ${gdvReport.comparables_summary.price_range}` : ''}
${gdvReport.comparables_summary.average ? `- **Average:** ${formatPrice(gdvReport.comparables_summary.average)}` : ''}
${gdvReport.comparables_summary.median ? `- **Median:** ${formatPrice(gdvReport.comparables_summary.median)}` : ''}

${gdvReport.comparables && gdvReport.comparables.length > 0 ? `### Land Registry Transactions

| Address | Price | Date | Type | Tenure |
|---------|-------|------|------|--------|
${gdvReport.comparables.map(c => `| [${c.address}](${c.land_registry_url}) | ${formatPrice(c.price)} | ${c.sale_date} | ${c.property_type} | ${c.tenure} |`).join('\n')}` : ''}

---

## Confidence Statement

${gdvReport.confidence_statement}

---

## Limitations & Caveats

${gdvReport.limitations.map(l => `- ${l}`).join('\n')}

---

**Data Sources:** ${gdvReport.data_sources.join(', ')}
`;

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `gdv-report-${property.postcode?.replace(/\s+/g, '-') || propertyId}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function handleFloorplanUpload() {
    if (!floorplanFile) return;

    try {
      setUploadingFloorplan(true);
      setError(null);

      const result = await uploadFloorplan(propertyId, floorplanFile);
      setFloorplanAnalysis(result);
      setFloorplanFile(null);

      // Refresh property data
      await loadProperty();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze floorplan');
      console.error(err);
    } finally {
      setUploadingFloorplan(false);
    }
  }

  async function handleSaveAndRecalculate() {
    if (!property) return;

    try {
      setSaving(true);
      setError(null);

      const data: Record<string, unknown> = {};

      // Property core data
      if (postcode) data.postcode = postcode;
      if (city) data.city = city;

      if (verifiedTenure) data.verified_tenure = verifiedTenure;
      if (titleNumber) data.title_number = titleNumber;
      if (isSingleTitle) data.is_single_title = isSingleTitle === 'yes';
      if (verifiedUnits) data.verified_units = parseInt(verifiedUnits, 10);
      data.planning_checked = planningChecked;
      if (planningChecked) {
        data.planning_constraints = {
          conservation_area: conservationArea,
          listed_building: listedBuilding,
          article_4: article4,
        };
      }
      data.site_visited = siteVisited;
      if (siteVisited && conditionRating) data.condition_rating = conditionRating;
      if (structuralConcerns) data.structural_concerns = structuralConcerns;
      if (revisedPrice) data.revised_asking_price = parseInt(revisedPrice, 10);

      const result = await updateManualInput(propertyId, data);
      setAnalysis(result);

      // Refresh property data
      await loadProperty();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  function getPlanningPortalUrl(postcode: string): string {
    // Use the Planning Portal's search by postcode
    const encoded = encodeURIComponent(postcode.trim());
    return `https://www.planningportal.co.uk/find-your-local-planning-authority?postcode=${encoded}`;
  }

  function downloadReport() {
    if (!property) return;

    const report = {
      generated_at: new Date().toISOString(),
      property: {
        id: property.id,
        title: property.title,
        asking_price: property.asking_price,
        city: property.city,
        postcode: property.postcode,
        estimated_units: property.estimated_units,
        tenure: property.tenure,
        tenure_confidence: property.tenure_confidence,
        opportunity_score: property.opportunity_score,
        status: property.status,
        first_seen: property.first_seen,
        source_url: property.source_url,
      },
      manual_inputs: property.manual_inputs,
      analysis: analysis ? {
        original_score: analysis.original_score,
        adjusted_score: analysis.adjusted_score,
        original_recommendation: analysis.original_recommendation,
        updated_recommendation: analysis.updated_recommendation,
        confidence_level: analysis.confidence_level,
        cost_breakdown: analysis.cost_breakdown,
        net_benefit_per_unit: analysis.net_benefit_per_unit,
        blockers: analysis.blockers,
        warnings: analysis.warnings,
        positives: analysis.positives,
      } : null,
      gdv_report: gdvReport ? {
        total_gdv: gdvReport.total_gdv,
        gdv_range_low: gdvReport.gdv_range_low,
        gdv_range_high: gdvReport.gdv_range_high,
        gdv_confidence: gdvReport.gdv_confidence,
        gross_uplift: gdvReport.gross_uplift,
        gross_uplift_percent: gdvReport.gross_uplift_percent,
        net_uplift: gdvReport.net_uplift,
        net_uplift_percent: gdvReport.net_uplift_percent,
        net_profit_per_unit: gdvReport.net_profit_per_unit,
        total_costs: gdvReport.total_costs,
        unit_valuations: gdvReport.unit_valuations,
        comparables_summary: gdvReport.comparables_summary,
        confidence_statement: gdvReport.confidence_statement,
        limitations: gdvReport.limitations,
        data_sources: gdvReport.data_sources,
      } : null,
      floorplan_analysis: floorplanAnalysis,
    };

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `property-report-${property.postcode?.replace(/\s+/g, '-') || property.id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading property...</p>
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="min-h-screen flex items-center justify-center flex-col gap-4 p-8">
        <p className="text-red-500 text-center max-w-md">{error || 'Property not found'}</p>
        <Button variant="outline" onClick={() => router.push('/')}>
          &larr; Back to Dashboard
        </Button>
        <Button variant="ghost" onClick={() => loadProperty()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <Button variant="ghost" onClick={() => router.push('/')} className="mb-2">
            &larr; Back to Dashboard
          </Button>
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-xl font-bold">{property.title}</h1>
              <p className="text-sm text-gray-500">
                {property.city} {property.postcode}
              </p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold">{formatPrice(property.asking_price)}</p>
              <div className="flex items-center gap-2 justify-end mt-1">
                <div className={`w-3 h-3 rounded-full ${getScoreColor(property.opportunity_score)}`} />
                <span className="text-sm font-medium">Score: {property.opportunity_score}/100</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Current Data */}
        <Card>
          <CardHeader>
            <CardTitle>Current Data (Scraped)</CardTitle>
            <CardDescription>Data extracted from the listing - verify and update below</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-gray-500">Est. Units</p>
                <p className="font-semibold">{property.estimated_units}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Tenure</p>
                <p className="font-semibold capitalize">{property.tenure}</p>
                <p className="text-xs text-gray-400">{Math.round(property.tenure_confidence * 100)}% confidence</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Status</p>
                <Badge variant="outline">{property.status}</Badge>
              </div>
              <div>
                <p className="text-xs text-gray-500">First Seen</p>
                <p className="text-sm">{new Date(property.first_seen).toLocaleDateString()}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <a
                href={property.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:underline"
              >
                View Original Listing &rarr;
              </a>
              {property.postcode && (
                <a
                  href={getPlanningPortalUrl(property.postcode)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-purple-600 hover:underline"
                >
                  Planning Portal &rarr;
                </a>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={downloadReport}
                className="ml-auto"
              >
                Download Report (JSON)
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Manual Verification Form */}
        <Card>
          <CardHeader>
            <CardTitle>Manual Verification</CardTitle>
            <CardDescription>
              Add verified data to improve the analysis. Each input will recalculate the recommendation.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Location Section - for missing data */}
            {(!property.postcode || !property.city) && (
              <div className="border-b pb-4 bg-yellow-50 -mx-6 px-6 py-4 -mt-6 mb-4">
                <h3 className="font-semibold mb-3 text-yellow-800">Missing Location Data</h3>
                <p className="text-sm text-yellow-700 mb-3">
                  Location data is required for GDV reports and valuations.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600 block mb-1">Postcode</label>
                    <Input
                      placeholder="e.g., PR8 1LY"
                      value={postcode}
                      onChange={(e) => setPostcode(e.target.value.toUpperCase())}
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600 block mb-1">City/Town</label>
                    <Input
                      placeholder="e.g., Southport"
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Title/Tenure Section */}
            <div className="border-b pb-4">
              <h3 className="font-semibold mb-3">Title & Tenure</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="text-sm text-gray-600 block mb-1">Verified Tenure</label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm"
                    value={verifiedTenure}
                    onChange={(e) => setVerifiedTenure(e.target.value)}
                  >
                    <option value="">-- Select --</option>
                    <option value="freehold">Freehold</option>
                    <option value="leasehold">Leasehold</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm text-gray-600 block mb-1">Title Number</label>
                  <Input
                    placeholder="e.g., TGL123456"
                    value={titleNumber}
                    onChange={(e) => setTitleNumber(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600 block mb-1">Single Title?</label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm"
                    value={isSingleTitle}
                    onChange={(e) => setIsSingleTitle(e.target.value)}
                  >
                    <option value="">-- Select --</option>
                    <option value="yes">Yes - Single Title</option>
                    <option value="no">No - Multiple Titles</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Units Section */}
            <div className="border-b pb-4">
              <h3 className="font-semibold mb-3">Units</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-gray-600 block mb-1">Verified Number of Units</label>
                  <Input
                    type="number"
                    min="1"
                    placeholder="e.g., 4"
                    value={verifiedUnits}
                    onChange={(e) => setVerifiedUnits(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600 block mb-1">Revised Asking Price</label>
                  <Input
                    type="number"
                    placeholder={property.asking_price.toString()}
                    value={revisedPrice}
                    onChange={(e) => setRevisedPrice(e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Planning Section */}
            <div className="border-b pb-4">
              <h3 className="font-semibold mb-3">Planning</h3>
              <div className="space-y-3">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={planningChecked}
                    onChange={(e) => setPlanningChecked(e.target.checked)}
                  />
                  <span className="text-sm">Planning portal checked</span>
                </label>
                {planningChecked && (
                  <div className="ml-6 space-y-2">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={conservationArea}
                        onChange={(e) => setConservationArea(e.target.checked)}
                      />
                      <span className="text-sm">Conservation Area</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={listedBuilding}
                        onChange={(e) => setListedBuilding(e.target.checked)}
                      />
                      <span className="text-sm">Listed Building</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={article4}
                        onChange={(e) => setArticle4(e.target.checked)}
                      />
                      <span className="text-sm">Article 4 Direction</span>
                    </label>
                  </div>
                )}
              </div>
            </div>

            {/* Site Visit Section */}
            <div className="border-b pb-4">
              <h3 className="font-semibold mb-3">Site Visit</h3>
              <div className="space-y-3">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={siteVisited}
                    onChange={(e) => setSiteVisited(e.target.checked)}
                  />
                  <span className="text-sm">Site visited</span>
                </label>
                {siteVisited && (
                  <div className="ml-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-gray-600 block mb-1">Condition Rating</label>
                      <select
                        className="w-full border rounded-md px-3 py-2 text-sm"
                        value={conditionRating}
                        onChange={(e) => setConditionRating(e.target.value)}
                      >
                        <option value="">-- Select --</option>
                        <option value="excellent">Excellent</option>
                        <option value="good">Good</option>
                        <option value="fair">Fair</option>
                        <option value="poor">Poor</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-sm text-gray-600 block mb-1">Structural Concerns</label>
                      <Input
                        placeholder="Any structural issues?"
                        value={structuralConcerns}
                        onChange={(e) => setStructuralConcerns(e.target.value)}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Floorplan Analysis Section */}
            <div className="border-b pb-4">
              <h3 className="font-semibold mb-3">Floorplan Analysis</h3>
              <p className="text-sm text-gray-500 mb-3">
                Upload a floorplan image for AI-powered room detection and layout analysis
              </p>
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <Input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    onChange={(e) => setFloorplanFile(e.target.files?.[0] || null)}
                    className="flex-1"
                  />
                  <Button
                    onClick={handleFloorplanUpload}
                    disabled={!floorplanFile || uploadingFloorplan}
                    variant="outline"
                  >
                    {uploadingFloorplan ? 'Analyzing...' : 'Analyze'}
                  </Button>
                </div>
                {floorplanFile && (
                  <p className="text-sm text-gray-500">
                    Selected: {floorplanFile.name} ({(floorplanFile.size / 1024).toFixed(1)} KB)
                  </p>
                )}

                {/* Existing Floorplan Analysis Results */}
                {floorplanAnalysis && (
                  <div className="space-y-3 mt-4">
                    <div className="p-4 bg-purple-50 border border-purple-200 rounded-lg">
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <p className="font-semibold text-purple-800">Floorplan Analysis Results</p>
                          {floorplanAnalysis.analyzed_at && (
                            <p className="text-xs text-purple-600">
                              Analyzed: {new Date(floorplanAnalysis.analyzed_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                        <Badge
                          variant={floorplanAnalysis.suitable_for_title_split ? 'default' : 'destructive'}
                        >
                          {floorplanAnalysis.suitable_for_title_split ? 'Suitable' : 'Not Suitable'}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-3">
                        <div>
                          <p className="text-xs text-gray-500">Units Detected</p>
                          <p className="text-xl font-bold text-purple-700">{floorplanAnalysis.units_detected}</p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500">Confidence</p>
                          <p className="font-semibold">{Math.round(floorplanAnalysis.confidence * 100)}%</p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500">Self-Contained</p>
                          <p className="font-semibold">
                            {floorplanAnalysis.self_contained_assessment.all_self_contained ? 'Yes' : 'No'}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Unit Details */}
                    {floorplanAnalysis.units.length > 0 && (
                      <div className="p-4 bg-gray-50 border rounded-lg">
                        <p className="font-semibold mb-2">Unit Breakdown</p>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-left text-gray-500 border-b">
                                <th className="pb-2">Unit</th>
                                <th className="pb-2">Layout</th>
                                <th className="pb-2 text-center">Beds</th>
                                <th className="pb-2 text-center">Baths</th>
                                <th className="pb-2 text-center">Reception</th>
                                <th className="pb-2">Notes</th>
                              </tr>
                            </thead>
                            <tbody>
                              {floorplanAnalysis.units.map((unit, i) => (
                                <tr key={i} className="border-b border-gray-100">
                                  <td className="py-2 font-medium">{unit.unit_id}</td>
                                  <td className="py-2">{unit.layout_type}</td>
                                  <td className="py-2 text-center">{unit.bedrooms}</td>
                                  <td className="py-2 text-center">{unit.bathrooms}</td>
                                  <td className="py-2 text-center">{unit.reception_rooms}</td>
                                  <td className="py-2 text-xs text-gray-500">{unit.notes || '-'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Concerns */}
                    {(floorplanAnalysis.layout_concerns.length > 0 ||
                      floorplanAnalysis.self_contained_assessment.concerns.length > 0) && (
                      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                        <p className="font-semibold text-yellow-800 mb-2">Concerns</p>
                        <ul className="text-sm text-yellow-700 space-y-1">
                          {floorplanAnalysis.self_contained_assessment.concerns.map((c, i) => (
                            <li key={`sc-${i}`}>- {c}</li>
                          ))}
                          {floorplanAnalysis.layout_concerns.map((c, i) => (
                            <li key={`lc-${i}`}>- {c}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Analysis Notes */}
                    {floorplanAnalysis.analysis_notes && (
                      <div className="p-4 bg-gray-100 border rounded-lg">
                        <p className="font-semibold mb-2">Analysis Notes</p>
                        <p className="text-sm text-gray-600">{floorplanAnalysis.analysis_notes}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
                {error}
              </div>
            )}

            <Button onClick={handleSaveAndRecalculate} disabled={saving} className="w-full">
              {saving ? 'Saving & Recalculating...' : 'Save & Recalculate Analysis'}
            </Button>
          </CardContent>
        </Card>

        {/* Analysis Results */}
        {analysis && (
          <Card>
            <CardHeader>
              <CardTitle>Recalculated Analysis</CardTitle>
              <CardDescription>
                Analysis updated with your manual inputs
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Score Change */}
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-sm text-gray-500">Original Score</p>
                  <p className="text-2xl font-bold">{analysis.original_score}</p>
                  <Badge variant="outline">{analysis.original_recommendation}</Badge>
                </div>
                <div className="text-3xl text-gray-400">&rarr;</div>
                <div className="text-right">
                  <p className="text-sm text-gray-500">Adjusted Score</p>
                  <p className="text-2xl font-bold">{analysis.adjusted_score}</p>
                  <Badge
                    variant={
                      analysis.updated_recommendation === 'proceed'
                        ? 'default'
                        : analysis.updated_recommendation === 'review'
                        ? 'secondary'
                        : 'destructive'
                    }
                  >
                    {analysis.updated_recommendation.toUpperCase()}
                  </Badge>
                </div>
              </div>

              {/* Blockers */}
              {analysis.blockers.length > 0 && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="font-semibold text-red-800 mb-2">Deal Blockers</p>
                  <ul className="text-sm text-red-700 space-y-1">
                    {analysis.blockers.map((b: { type?: string; reason?: string }, i: number) => (
                      <li key={i}>- {b.reason || b.type}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Warnings */}
              {analysis.warnings.length > 0 && (
                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="font-semibold text-yellow-800 mb-2">Warnings</p>
                  <ul className="text-sm text-yellow-700 space-y-1">
                    {analysis.warnings.map((w: string, i: number) => (
                      <li key={i}>- {w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Positives */}
              {analysis.positives.length > 0 && (
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <p className="font-semibold text-green-800 mb-2">Positives</p>
                  <ul className="text-sm text-green-700 space-y-1">
                    {analysis.positives.map((p: string, i: number) => (
                      <li key={i}>+ {p}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Cost Breakdown */}
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="font-semibold text-blue-800 mb-2">Cost Breakdown</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div>
                    <p className="text-xs text-gray-500">Land Registry/unit</p>
                    <p className="font-medium">£{analysis.cost_breakdown.land_registry_per_unit}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Legal/unit</p>
                    <p className="font-medium">£{analysis.cost_breakdown.legal_per_unit}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Survey/unit</p>
                    <p className="font-medium">£{analysis.cost_breakdown.survey_per_unit}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Total Costs</p>
                    <p className="font-semibold">{formatPrice(analysis.cost_breakdown.total)}</p>
                  </div>
                </div>
              </div>

              {/* Net Benefit */}
              <div className="text-center p-4 bg-gray-100 rounded-lg">
                <p className="text-sm text-gray-500">Net Benefit Per Unit</p>
                <p className={`text-3xl font-bold ${analysis.net_benefit_per_unit >= 2000 ? 'text-green-600' : 'text-red-600'}`}>
                  {formatPrice(analysis.net_benefit_per_unit)}
                </p>
                <p className="text-xs text-gray-400">
                  Confidence: {analysis.confidence_level}
                </p>
              </div>

              {/* Impact Details */}
              {analysis.impacts.length > 0 && (
                <div>
                  <p className="font-semibold mb-2">Impact Details</p>
                  <div className="space-y-2">
                    {analysis.impacts.map((impact, i) => (
                      <div
                        key={i}
                        className={`p-2 rounded text-sm ${
                          impact.impact_type === 'blocker'
                            ? 'bg-red-50 text-red-700'
                            : impact.impact_type === 'warning'
                            ? 'bg-yellow-50 text-yellow-700'
                            : impact.impact_type === 'positive'
                            ? 'bg-green-50 text-green-700'
                            : 'bg-gray-50 text-gray-700'
                        }`}
                      >
                        <span className="font-medium">{impact.score_adjustment > 0 ? '+' : ''}{impact.score_adjustment}</span>
                        {' '}{impact.message}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* GDV Report Section */}
        <Card>
          <CardHeader>
            <CardTitle>Lender-Grade GDV Report</CardTitle>
            <CardDescription>
              Generate a comprehensive GDV report with Land Registry comparables and EPC data for lender presentations
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800">
                <strong>Data Sources:</strong> HM Land Registry Price Paid Data, PropertyData.co.uk AVM, UK House Price Index, EPC Register
              </p>
            </div>

            <div className="flex gap-2">
              <Button
                onClick={handleGenerateGDVReport}
                disabled={generatingReport}
                className="flex-1"
                variant="outline"
              >
                {generatingReport ? 'Generating Report...' : 'Generate GDV Report'}
              </Button>
              {gdvReport && (
                <Button
                  onClick={downloadGDVReportMarkdown}
                  variant="secondary"
                >
                  Download MD
                </Button>
              )}
            </div>

            {gdvReport && (
              <div className="space-y-4 mt-4">
                {/* GDV Summary */}
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <p className="font-semibold text-green-800">GDV Summary</p>
                      <p className="text-xs text-green-600">{gdvReport.data_freshness}</p>
                    </div>
                    <Badge variant={gdvReport.gdv_confidence === 'high' ? 'default' : gdvReport.gdv_confidence === 'medium' ? 'secondary' : 'outline'}>
                      {gdvReport.gdv_confidence.toUpperCase()} Confidence
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div>
                      <p className="text-xs text-gray-500">Total GDV</p>
                      <p className="text-xl font-bold text-green-700">{formatPrice(gdvReport.total_gdv)}</p>
                      <p className="text-xs text-gray-400">
                        {formatPrice(gdvReport.gdv_range_low)} - {formatPrice(gdvReport.gdv_range_high)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">75% LTV</p>
                      <p className="text-lg font-bold text-blue-700">{formatPrice(Math.round(gdvReport.total_gdv * 0.75))}</p>
                      <p className="text-xs text-gray-400">Max loan at 75%</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Asking Price</p>
                      <p className="font-semibold">{formatPrice(gdvReport.asking_price)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Gross Uplift</p>
                      <p className="font-semibold text-green-600">{formatPrice(gdvReport.gross_uplift)}</p>
                      <p className="text-xs text-gray-400">{gdvReport.gross_uplift_percent}%</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Net Uplift</p>
                      <p className="font-semibold text-green-600">{formatPrice(gdvReport.net_uplift)}</p>
                      <p className="text-xs text-gray-400">{gdvReport.net_uplift_percent}%</p>
                    </div>
                  </div>
                </div>

                {/* Unit Valuations */}
                <div className="p-4 bg-gray-50 border rounded-lg">
                  <p className="font-semibold mb-3">Unit-by-Unit Valuations</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-2">Unit</th>
                          <th className="pb-2">Beds</th>
                          <th className="pb-2 text-right">Value</th>
                          <th className="pb-2 text-right">Range</th>
                          <th className="pb-2 text-center">Confidence</th>
                          <th className="pb-2">Method</th>
                        </tr>
                      </thead>
                      <tbody>
                        {gdvReport.unit_valuations.map((unit, i) => (
                          <tr key={i} className="border-b border-gray-100">
                            <td className="py-2 font-medium">{unit.unit_identifier}</td>
                            <td className="py-2">{unit.beds || '-'}</td>
                            <td className="py-2 text-right font-semibold">{formatPrice(unit.estimated_value)}</td>
                            <td className="py-2 text-right text-xs text-gray-500">
                              {formatPrice(unit.value_range_low)} - {formatPrice(unit.value_range_high)}
                            </td>
                            <td className="py-2 text-center">
                              <Badge variant={unit.confidence === 'high' ? 'default' : unit.confidence === 'medium' ? 'secondary' : 'outline'} className="text-xs">
                                {unit.confidence}
                              </Badge>
                            </td>
                            <td className="py-2 text-xs text-gray-500">{unit.primary_method}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Costs & Net Profit */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-orange-50 border border-orange-200 rounded-lg">
                    <p className="font-semibold text-orange-800 mb-2">Title Split Costs</p>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span>Base costs</span>
                        <span>{formatPrice(gdvReport.title_split_costs)}</span>
                      </div>
                      {gdvReport.refurbishment_budget && (
                        <div className="flex justify-between">
                          <span>Refurbishment</span>
                          <span>{formatPrice(gdvReport.refurbishment_budget)}</span>
                        </div>
                      )}
                      <div className="flex justify-between font-semibold pt-1 border-t border-orange-200">
                        <span>Total</span>
                        <span>{formatPrice(gdvReport.total_costs)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="p-4 bg-green-100 border border-green-300 rounded-lg">
                    <p className="font-semibold text-green-800 mb-2">Net Profit Analysis</p>
                    <div className="text-center">
                      <p className="text-3xl font-bold text-green-700">{formatPrice(gdvReport.net_profit_per_unit)}</p>
                      <p className="text-sm text-green-600">per unit</p>
                      <p className="text-xs text-gray-500 mt-1">
                        Total: {formatPrice(gdvReport.net_uplift)} ({gdvReport.net_uplift_percent}% return)
                      </p>
                    </div>
                  </div>
                </div>

                {/* Comparables Summary */}
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="font-semibold text-blue-800 mb-2">Comparable Evidence</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
                    <div>
                      <p className="text-xs text-gray-500">Total Comparables</p>
                      <p className="font-semibold">{gdvReport.comparables_summary.count}</p>
                    </div>
                    {gdvReport.comparables_summary.price_range && (
                      <div>
                        <p className="text-xs text-gray-500">Price Range</p>
                        <p className="font-semibold">{gdvReport.comparables_summary.price_range}</p>
                      </div>
                    )}
                    {gdvReport.comparables_summary.average && (
                      <div>
                        <p className="text-xs text-gray-500">Average</p>
                        <p className="font-semibold">{formatPrice(gdvReport.comparables_summary.average)}</p>
                      </div>
                    )}
                    {gdvReport.comparables_summary.median && (
                      <div>
                        <p className="text-xs text-gray-500">Median</p>
                        <p className="font-semibold">{formatPrice(gdvReport.comparables_summary.median)}</p>
                      </div>
                    )}
                  </div>

                  {/* Individual Comparables Table */}
                  {gdvReport.comparables && gdvReport.comparables.length > 0 && (
                    <div className="overflow-x-auto border-t border-blue-200 pt-3">
                      <p className="text-xs text-blue-700 mb-2 font-medium">Land Registry Transactions</p>
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-500 border-b">
                            <th className="pb-2">Address</th>
                            <th className="pb-2 text-right">Price</th>
                            <th className="pb-2 text-center">Date</th>
                            <th className="pb-2 text-center">Type</th>
                            <th className="pb-2 text-center">Tenure</th>
                          </tr>
                        </thead>
                        <tbody>
                          {gdvReport.comparables.map((comp, i) => (
                            <tr key={i} className="border-b border-blue-100">
                              <td className="py-2 text-xs">
                                <a
                                  href={comp.land_registry_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 hover:underline"
                                >
                                  {comp.address}
                                </a>
                              </td>
                              <td className="py-2 text-right font-semibold">{formatPrice(comp.price)}</td>
                              <td className="py-2 text-center text-xs text-gray-500">{comp.sale_date}</td>
                              <td className="py-2 text-center text-xs">{comp.property_type}</td>
                              <td className="py-2 text-center text-xs">{comp.tenure}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Confidence Statement */}
                <div className="p-4 bg-gray-100 border rounded-lg">
                  <p className="font-semibold mb-2">Confidence Statement</p>
                  <p className="text-sm text-gray-600 whitespace-pre-line">{gdvReport.confidence_statement}</p>
                </div>

                {/* Limitations */}
                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="font-semibold text-yellow-800 mb-2">Limitations & Caveats</p>
                  <ul className="text-sm text-yellow-700 space-y-1">
                    {gdvReport.limitations.map((limitation, i) => (
                      <li key={i}>- {limitation}</li>
                    ))}
                  </ul>
                </div>

                {/* Data Sources */}
                <div className="text-xs text-gray-500">
                  <p><strong>Data Sources:</strong> {gdvReport.data_sources.join(', ')}</p>
                  <p><strong>Report Date:</strong> {new Date(gdvReport.report_date).toLocaleString()}</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
