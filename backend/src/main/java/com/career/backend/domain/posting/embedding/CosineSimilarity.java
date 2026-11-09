package com.career.backend.domain.posting.embedding;

public final class CosineSimilarity {
    private CosineSimilarity() {}
    public static boolean valid(double[] vector,int dimension) {
        if(vector==null||vector.length!=dimension)return false;
        double norm=0;
        for(double v:vector){if(!Double.isFinite(v)||Math.abs(v)>3.4e38)return false;norm+=v*v;}
        return norm>0&&Double.isFinite(norm);
    }
    public static double cosine(double[] a,double[] b) {
        if(!valid(a,b==null?0:b.length)||!valid(b,a.length))throw new IllegalArgumentException("INVALID_VECTOR");
        double dot=0,aa=0,bb=0;
        for(int i=0;i<a.length;i++){dot+=a[i]*b[i];aa+=a[i]*a[i];bb+=b[i]*b[i];}
        return Math.max(-1,Math.min(1,dot/(Math.sqrt(aa)*Math.sqrt(bb))));
    }
}
