/**
 * The full model catalog as a browsable list: every provider pi knows about
 * (not only the logged-in ones), every model under it, and whether it is usable
 * right now. Pure functions over the registry's models so they test without pi.
 */

export interface CatalogModel {
	id: string;
	name: string;
	provider: string;
	reasoning?: boolean;
	contextWindow?: number;
	cost?: { input?: number; output?: number };
}

export interface ProviderEntry {
	provider: string;
	authed: boolean;
	models: CatalogModel[];
}

/** Providers with at least one usable model first, then alphabetical. */
export function catalogByProvider(models: readonly CatalogModel[], isUsable: (model: CatalogModel) => boolean): ProviderEntry[] {
	const byProvider = new Map<string, CatalogModel[]>();
	for (const model of models) {
		const list = byProvider.get(model.provider) ?? [];
		list.push(model);
		byProvider.set(model.provider, list);
	}
	return [...byProvider.entries()]
		.map(([provider, list]) => ({
			provider,
			authed: list.some(isUsable),
			models: [...list].sort((a, b) => a.id.localeCompare(b.id)),
		}))
		.sort((a, b) => Number(b.authed) - Number(a.authed) || a.provider.localeCompare(b.provider));
}

export function providerLabel(entry: ProviderEntry): string {
	const count = `${entry.models.length} model${entry.models.length === 1 ? "" : "s"}`;
	return entry.authed ? `✓ ${entry.provider} — ${count}` : `🔒 ${entry.provider} — ${count} · /login ${entry.provider}`;
}

function money(value: number | undefined): string {
	return value === undefined ? "?" : value === 0 ? "0" : value < 1 ? value.toFixed(2).replace(/0$/, "") : String(+value.toFixed(2));
}

export function modelLabel(model: CatalogModel, usable: boolean): string {
	const parts = [`${usable ? "✓" : "🔒"} ${model.provider}/${model.id}`, model.name && model.name !== model.id ? model.name : ""];
	if (model.contextWindow) parts.push(`${Math.round(model.contextWindow / 1000)}k ctx`);
	if (model.cost && (model.cost.input !== undefined || model.cost.output !== undefined)) parts.push(`$${money(model.cost.input)}/$${money(model.cost.output)} per M`);
	if (model.reasoning) parts.push("reasoning");
	return parts.filter(Boolean).join(" · ");
}

/** Every word must appear in provider/id/name (case-insensitive). Usable models first. */
export function searchModels(models: readonly CatalogModel[], query: string, isUsable: (model: CatalogModel) => boolean): CatalogModel[] {
	const words = query.toLowerCase().split(/\s+/).filter(Boolean);
	if (!words.length) return [];
	return models
		.filter((model) => {
			const haystack = `${model.provider}/${model.id} ${model.name}`.toLowerCase();
			return words.every((word) => haystack.includes(word));
		})
		.sort((a, b) => Number(isUsable(b)) - Number(isUsable(a)) || `${a.provider}/${a.id}`.localeCompare(`${b.provider}/${b.id}`));
}

export function loginHint(provider: string): string {
	return `${provider} is not logged in. Run /login ${provider} in pi (or add its API key), then pick the model again.`;
}
