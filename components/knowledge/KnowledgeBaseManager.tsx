'use client';

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Brain,
    Upload,
    Search,
    FileText,
    Trash2,
    Plus,
    FolderUp,
    CheckCircle,
    XCircle,
    Database,
    Eye
} from 'lucide-react';

const KB_API = 'http://127.0.0.1:8000';

export default function KnowledgeBaseManager() {
    const [stats, setStats] = useState<{ total_chunks: number }>({ total_chunks: 0 });
    const [documents, setDocuments] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);

    // Form state
    const [content, setContent] = useState('');

    // Search state
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [searching, setSearching] = useState(false);

    // File upload state
    const [uploadingFiles, setUploadingFiles] = useState(false);
    const [fileResults, setFileResults] = useState<any[]>([]);
    const [dragActive, setDragActive] = useState(false);

    // View all content
    const [allContent, setAllContent] = useState('');
    const [viewingAll, setViewingAll] = useState(false);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            // Get stats
            const statsRes = await fetch(`${KB_API}/knowledge/stats`);
            const statsData = await statsRes.json();
            if (statsData.success) {
                setStats(statsData.stats);
            }

            // Get documents
            const docsRes = await fetch(`${KB_API}/knowledge/list/knowledge?limit=100`);
            const docsData = await docsRes.json();
            if (docsData.success) {
                setDocuments(docsData.documents);
            }
        } catch (error) {
            console.error('Error fetching data:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    async function handleUpload() {
        if (!content.trim()) return;

        setUploading(true);
        try {
            const res = await fetch(`${KB_API}/knowledge/upload`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ collection: 'knowledge', content }),
            });
            const result = await res.json();

            if (result.success) {
                setContent('');
                fetchData();
            } else {
                alert('Error: ' + result.error);
            }
        } catch (error) {
            console.error('Upload error:', error);
        } finally {
            setUploading(false);
        }
    }

    async function handleSearch() {
        if (!searchQuery.trim()) return;

        setSearching(true);
        try {
            const res = await fetch(`${KB_API}/knowledge/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: searchQuery, n_results: 10 }),
            });
            const result = await res.json();
            setSearchResults(result.results || []);
        } catch (error) {
            console.error('Search error:', error);
        } finally {
            setSearching(false);
        }
    }

    async function handleDelete(docId: string) {
        if (!confirm('¿Eliminar este documento?')) return;

        try {
            await fetch(`${KB_API}/knowledge/delete/knowledge/${docId}`, {
                method: 'DELETE',
            });
            fetchData();
        } catch (error) {
            console.error('Delete error:', error);
        }
    }

    async function handleFileUpload(files: FileList | null) {
        if (!files || files.length === 0) return;

        setUploadingFiles(true);
        setFileResults([]);

        try {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }

            const res = await fetch(`${KB_API}/knowledge/upload-files?collection=knowledge`, {
                method: 'POST',
                body: formData,
            });

            const data = await res.json();
            setFileResults(data.results || []);
            fetchData();
        } catch (error) {
            console.error('File upload error:', error);
            setFileResults([{ filename: 'Error', success: false, error: String(error) }]);
        } finally {
            setUploadingFiles(false);
        }
    }

    function handleDrag(e: React.DragEvent) {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    }

    function handleDrop(e: React.DragEvent) {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        handleFileUpload(e.dataTransfer.files);
    }

    async function handleViewAll() {
        setViewingAll(true);
        try {
            // Combine all document previews
            const allText = documents.map(d => `📄 ${d.title}\n${d.preview}`).join('\n\n---\n\n');
            setAllContent(allText);
        } catch (error) {
            console.error('Error viewing all:', error);
        }
    }

    return (
        <div className="space-y-6">
            {/* Header Stats */}
            <Card className="bg-gradient-to-br from-purple-500/10 to-blue-500/10 border-purple-500/20">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Brain className="h-6 w-6 text-purple-400" />
                        Base de Conocimiento - Value Investing AI
                    </CardTitle>
                    <CardDescription>
                        Tu agente aprende de todo lo que subas aquí
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-4">
                        <Badge variant="default" className="px-4 py-2 text-base">
                            <Database className="h-4 w-4 mr-2" />
                            {stats.total_chunks || 0} chunks de conocimiento
                        </Badge>
                        <Badge variant="secondary" className="px-3 py-1.5">
                            <FileText className="h-3 w-3 mr-1" />
                            {documents.length} documentos
                        </Badge>
                    </div>
                </CardContent>
            </Card>

            <Tabs defaultValue="upload" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="upload" className="flex items-center gap-2">
                        <Upload className="h-4 w-4" />
                        Subir
                    </TabsTrigger>
                    <TabsTrigger value="browse" className="flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        Ver Todo
                    </TabsTrigger>
                    <TabsTrigger value="search" className="flex items-center gap-2">
                        <Search className="h-4 w-4" />
                        Buscar
                    </TabsTrigger>
                    <TabsTrigger value="preview" className="flex items-center gap-2">
                        <Eye className="h-4 w-4" />
                        Preview
                    </TabsTrigger>
                </TabsList>

                {/* Upload Tab */}
                <TabsContent value="upload">
                    <div className="space-y-4">
                        {/* Drag & Drop File Zone */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <FolderUp className="h-5 w-5" />
                                    Subir Archivos
                                </CardTitle>
                                <CardDescription>
                                    Arrastra PDFs, TXTs o documentos de texto
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div
                                    onDragEnter={handleDrag}
                                    onDragLeave={handleDrag}
                                    onDragOver={handleDrag}
                                    onDrop={handleDrop}
                                    className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${dragActive
                                        ? 'border-purple-500 bg-purple-500/10'
                                        : 'border-gray-600 hover:border-gray-500'
                                        }`}
                                >
                                    <input
                                        type="file"
                                        id="file-upload"
                                        multiple
                                        accept=".pdf,.txt,.md,.xlsx,.xls,.docx"
                                        className="hidden"
                                        onChange={(e) => handleFileUpload(e.target.files)}
                                    />
                                    <label
                                        htmlFor="file-upload"
                                        className="cursor-pointer flex flex-col items-center gap-3"
                                    >
                                        <FolderUp className="h-12 w-12 text-gray-400" />
                                        <div>
                                            <p className="text-lg font-medium">
                                                {uploadingFiles ? 'Subiendo...' : 'Arrastra archivos aquí'}
                                            </p>
                                            <p className="text-sm text-muted-foreground">
                                                PDF, Excel, Word, TXT, MD
                                            </p>
                                        </div>
                                    </label>
                                </div>

                                {fileResults.length > 0 && (
                                    <div className="mt-4 space-y-2">
                                        {fileResults.map((r, i) => (
                                            <div
                                                key={i}
                                                className={`flex items-center gap-2 p-2 rounded text-sm ${r.success ? 'bg-green-500/10' : 'bg-red-500/10'
                                                    }`}
                                            >
                                                {r.success ? (
                                                    <CheckCircle className="h-4 w-4 text-green-500" />
                                                ) : (
                                                    <XCircle className="h-4 w-4 text-red-500" />
                                                )}
                                                <span className="font-medium">{r.filename}</span>
                                                {r.success ? (
                                                    <span className="text-muted-foreground">
                                                        {r.chunks_added} chunks añadidos
                                                    </span>
                                                ) : (
                                                    <span className="text-red-400">{r.error}</span>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Manual text input */}
                        <Card>
                            <CardHeader>
                                <CardTitle>Añadir Texto</CardTitle>
                                <CardDescription>
                                    Pega cualquier texto: análisis, notas, criterios, extractos de libros...
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <Textarea
                                    placeholder="Pega aquí tu conocimiento. Todo lo que añadas será usado por la IA para mejorar sus análisis..."
                                    value={content}
                                    onChange={(e) => setContent(e.target.value)}
                                    rows={10}
                                    className="font-mono text-sm"
                                />

                                <Button
                                    onClick={handleUpload}
                                    disabled={!content.trim() || uploading}
                                    className="w-full"
                                >
                                    <Plus className="h-4 w-4 mr-2" />
                                    {uploading ? 'Añadiendo...' : 'Añadir a la Base de Conocimiento'}
                                </Button>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                {/* Browse Tab */}
                <TabsContent value="browse">
                    <Card>
                        <CardHeader>
                            <CardTitle>Todos los Documentos ({documents.length})</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {loading ? (
                                <p className="text-muted-foreground">Cargando...</p>
                            ) : documents.length === 0 ? (
                                <p className="text-muted-foreground text-center py-8">
                                    No hay documentos. ¡Sube tu primer análisis!
                                </p>
                            ) : (
                                <ScrollArea className="h-[500px]">
                                    <div className="space-y-2">
                                        {documents.map((doc) => (
                                            <div
                                                key={doc.id}
                                                className="flex items-start justify-between p-3 rounded-lg border bg-card hover:bg-accent/50"
                                            >
                                                <div className="flex-1 min-w-0">
                                                    <p className="font-medium text-sm">
                                                        {doc.title || 'Sin título'}
                                                    </p>
                                                    <p className="text-xs text-muted-foreground line-clamp-2">
                                                        {doc.preview}
                                                    </p>
                                                    <div className="flex gap-2 mt-1">
                                                        <Badge variant="outline" className="text-xs">
                                                            {doc.chunks} chunks
                                                        </Badge>
                                                        {doc.added_at && (
                                                            <span className="text-xs text-muted-foreground">
                                                                {new Date(doc.added_at).toLocaleDateString('es-ES')}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleDelete(doc.id)}
                                                >
                                                    <Trash2 className="h-4 w-4 text-red-400" />
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Search Tab */}
                <TabsContent value="search">
                    <Card>
                        <CardHeader>
                            <CardTitle>Buscar en tu Conocimiento</CardTitle>
                            <CardDescription>
                                Búsqueda semántica - encuentra contenido por significado
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex gap-2">
                                <Input
                                    placeholder="Buscar... (ej: criterios ROIC, análisis Apple, margen seguridad)"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                                />
                                <Button onClick={handleSearch} disabled={searching}>
                                    <Search className="h-4 w-4" />
                                </Button>
                            </div>

                            {searchResults.length > 0 && (
                                <ScrollArea className="h-[400px]">
                                    <div className="space-y-3">
                                        {searchResults.map((result, i) => (
                                            <div
                                                key={i}
                                                className="p-3 rounded-lg border bg-card"
                                            >
                                                <div className="flex items-center gap-2 mb-2">
                                                    <Badge
                                                        variant={result.score > 0.7 ? 'default' : 'secondary'}
                                                        className="text-xs"
                                                    >
                                                        {(result.score * 100).toFixed(0)}% relevante
                                                    </Badge>
                                                </div>
                                                <p className="text-sm">{result.content}</p>
                                            </div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Preview Tab */}
                <TabsContent value="preview">
                    <Card>
                        <CardHeader>
                            <CardTitle>Vista Previa del Conocimiento</CardTitle>
                            <CardDescription>
                                Esto es lo que la IA "ve" cuando analiza acciones
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button onClick={handleViewAll} className="mb-4">
                                <Eye className="h-4 w-4 mr-2" />
                                Ver Todo el Conocimiento
                            </Button>

                            {allContent && (
                                <ScrollArea className="h-[400px]">
                                    <pre className="text-sm whitespace-pre-wrap font-mono bg-gray-900 p-4 rounded-lg">
                                        {allContent}
                                    </pre>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
