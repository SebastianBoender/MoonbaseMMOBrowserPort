// Read VM data without evaluating Lingo or entering its execution scopes.
window.moonbaseRead = {
  globals() { return JSON.parse(window.__vm.mcp_get_globals()).globals; },
  inspect(datum) {
    if (!datum || datum.datum_id == null) return datum || { value: 'Void' };
    return JSON.parse(window.__vm.mcp_inspect_datum(datum.datum_id));
  },
  string(datum) {
    const value = datum?.value || '';
    return value.startsWith('"') && value.endsWith('"') ? value.slice(1, -1) : value;
  },
  list(datum) {
    const value = this.inspect(datum).value || '';
    return Array.from(value.matchAll(/<DatumRef\((\d+|Void)\)>/g), match => match[1] === 'Void' ? {value:'Void'} : this.inspect({datum_id:Number(match[1])}));
  }
};
