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
  getPropertyDetail,
  updateManualInput,
  generateGDVReport,
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
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
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
      const data = await getPropertyDetail(propertyId);
      setProperty(data);

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
      }
    } catch (err) {
      setError('Failed to load property');
      console.error(err);
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

  async function handleSaveAndRecalculate() {
    if (!property) return;

    try {
      setSaving(true);
      setError(null);

      const data: Record<string, unknown> = {};

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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading property...</p>
      </div>
    );
  }

  if (!property) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-500">{error || 'Property not found'}</p>
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
            <div className="mt-4">
              <a
                href={property.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:underline"
              >
                View Original Listing &rarr;
              </a>
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

            <Button
              onClick={handleGenerateGDVReport}
              disabled={generatingReport}
              className="w-full"
              variant="outline"
            >
              {generatingReport ? 'Generating Report...' : 'Generate GDV Report'}
            </Button>

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
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-xs text-gray-500">Total GDV</p>
                      <p className="text-xl font-bold text-green-700">{formatPrice(gdvReport.total_gdv)}</p>
                      <p className="text-xs text-gray-400">
                        {formatPrice(gdvReport.gdv_range_low)} - {formatPrice(gdvReport.gdv_range_high)}
                      </p>
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
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
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
